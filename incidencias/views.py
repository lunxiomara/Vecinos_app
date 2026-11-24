import json
import time
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.models import Group
from django.contrib import messages
from django.db.models import Count, Q
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotFound, JsonResponse
from django.utils.dateparse import parse_date

from .models import Incidencia, Comentario, Perfil, Edificio, EventoIncidencia, Tecnico
from .forms import RegistroForm, IncidenciaResidenteForm, IncidenciaAdminForm, ComentarioForm, TecnicoForm
from .filters import IncidenciaFilter
from .observabilidad import obtener_estado_observabilidad, reiniciar_observabilidad 

def es_administrador(user):
    """Verifica si el usuario tiene rol de administrador o es superusuario."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    perfil = getattr(user, 'perfil', None)
    return perfil is not None and perfil.rol == 'administrador'


def obtener_edificio_usuario(request):
    """Devuelve el edificio activo asignado por el middleware o el perfil."""
    if hasattr(request, 'edificio_activo') and request.edificio_activo:
        return request.edificio_activo
    if request.user.is_authenticated and hasattr(request.user, 'perfil'):
        return request.user.perfil.edificio
    return None


class RegistroView(CreateView):
    template_name = 'incidencias/registro.html'
    form_class = RegistroForm
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        messages.success(self.request, "¡Tu cuenta ha sido creada exitosamente! Ya puedes iniciar sesión.")
        return super().form_valid(form)


class IncidenciaListView(LoginRequiredMixin, ListView):
    model = Incidencia
    template_name = 'incidencias/incidencia_list.html'
    context_object_name = 'incidencias'
    paginate_by = 6

    def get_queryset(self):
        user = self.request.user
        edificio = obtener_edificio_usuario(self.request)

        # Superusuario ve todo sin restricción de edificio
        if user.is_superuser:
            qs = Incidencia.objects.all().select_related('creador', 'creador__perfil', 'edificio')
        elif edificio:
            perfil = getattr(user, 'perfil', None)
            if perfil and perfil.rol in ('administrador', 'tecnico', 'auditor'):
                # Admin/Técnico/Auditor ve todas las incidencias de SU edificio
                qs = Incidencia.objects.del_edificio(edificio).select_related('creador', 'creador__perfil', 'edificio')
            else:
                # Residente solo ve sus incidencias dentro de su edificio
                qs = Incidencia.objects.del_edificio(edificio).filter(creador=user).select_related('creador', 'edificio')
        else:
            qs = Incidencia.objects.none()

        self.filterset = IncidenciaFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        edificio = obtener_edificio_usuario(self.request)
        context['filter'] = self.filterset
        context['es_admin'] = es_administrador(user)

        if user.is_superuser:
            base_qs = Incidencia.objects.all()
        elif edificio:
            perfil = getattr(user, 'perfil', None)
            if perfil and perfil.rol in ('administrador', 'tecnico', 'auditor'):
                base_qs = Incidencia.objects.del_edificio(edificio)
            else:
                base_qs = Incidencia.objects.del_edificio(edificio).filter(creador=user)
        else:
            base_qs = Incidencia.objects.none()

        context['total_incidencias'] = base_qs.count()
        context['total_pendientes'] = base_qs.filter(estado='pendiente').count()
        context['total_proceso'] = base_qs.filter(estado='proceso').count()
        context['total_resueltas'] = base_qs.filter(estado='resuelta').count()
        context['total_cerradas'] = base_qs.filter(estado='cerrada').count()
        context['edificio_activo'] = edificio
        return context


class IncidenciaDetailView(LoginRequiredMixin, DetailView):
    model = Incidencia
    template_name = 'incidencias/incidencia_detail.html'
    context_object_name = 'incidencia'

    def get_queryset(self):
        """
        Criterio de aceptación M2:
        Un residente de otro edificio recibe 404 en todas las rutas y endpoints.
        """
        user = self.request.user
        edificio = obtener_edificio_usuario(self.request)

        if user.is_superuser:
            return Incidencia.objects.all().select_related('creador', 'creador__perfil', 'edificio')
        
        if not edificio:
            return Incidencia.objects.none()

        perfil = getattr(user, 'perfil', None)
        if perfil and perfil.rol in ('administrador', 'tecnico', 'auditor'):
            return Incidencia.objects.del_edificio(edificio).select_related('creador', 'creador__perfil', 'edificio')
        
        # Residente: únicamente sus incidencias de su propio edificio
        return Incidencia.objects.del_edificio(edificio).filter(creador=user).select_related('creador', 'creador__perfil', 'edificio')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Filtrar comentarios internos según permiso
        comentarios_qs = self.object.comentarios.all().select_related('autor')
        if not self.request.user.has_perm('incidencias.ver_nota_interna', self.object):
            comentarios_qs = comentarios_qs.filter(es_interno=False)

        context['comentarios'] = comentarios_qs
        context['eventos'] = self.object.eventos.all().select_related('actor')
        context['comentario_form'] = ComentarioForm()
        context['es_admin'] = es_administrador(self.request.user)
        context['puede_cambiar_estado'] = self.request.user.has_perm('incidencias.cambiar_estado', self.object)
        context['puede_ver_nota_interna'] = self.request.user.has_perm('incidencias.ver_nota_interna', self.object)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        user = request.user

        # Permiso: residentes solo comentan en su propia incidencia del mismo edificio
        if not user.has_perm('incidencias.ver_incidencia', self.object):
            raise PermissionDenied("No tienes permiso para comentar en esta incidencia.")

        form = ComentarioForm(request.POST)
        if form.is_valid():
            comentario = form.save(commit=False)
            comentario.incidencia = self.object
            comentario.autor = user
            comentario.save()

            # Registrar evento inmutable de auditoría
            EventoIncidencia.objects.create(
                incidencia=self.object,
                tipo='comentario',
                actor=user,
                detalle=f"Comentario añadido por {user.username}"
            )

            messages.success(request, "Comentario publicado correctamente.")
            return redirect('incidencia_detail', pk=self.object.pk)

        context = self.get_context_data()
        context['comentario_form'] = form
        return self.render_to_response(context)


class IncidenciaCreateView(LoginRequiredMixin, CreateView):
    model = Incidencia
    form_class = IncidenciaResidenteForm
    template_name = 'incidencias/incidencia_form.html'
    success_url = reverse_lazy('incidencia_list')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm('incidencias.crear_incidencia'):
            messages.warning(request, "Solo los residentes y administradores pueden reportar incidencias.")
            return redirect('incidencia_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        edificio = obtener_edificio_usuario(self.request)
        if not edificio:
            messages.error(self.request, "Tu usuario no tiene un edificio asignado en su perfil.")
            return redirect('incidencia_list')

        form.instance.creador = self.request.user
        form.instance.edificio = edificio
        form.instance.estado = 'pendiente'
        response = super().form_valid(form)

        # Registro inmutable de auditoría (M1 & M2)
        EventoIncidencia.objects.create(
            incidencia=self.object,
            tipo='creacion',
            actor=self.request.user,
            estado_despues='pendiente',
            detalle=f"Incidencia creada por residente {self.request.user.username} en {edificio.nombre}"
        )

        messages.success(self.request, "Incidencia reportada con éxito en tu edificio.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo_accion'] = "Reportar Nueva Incidencia"
        return context


class IncidenciaUpdateView(LoginRequiredMixin, UpdateView):
    model = Incidencia
    template_name = 'incidencias/incidencia_form.html'
    success_url = reverse_lazy('incidencia_list')

    def get_queryset(self):
        edificio = obtener_edificio_usuario(self.request)
        if self.request.user.is_superuser:
            return Incidencia.objects.all()
        if not edificio:
            return Incidencia.objects.none()
        return Incidencia.objects.del_edificio(edificio)

    def get_form_class(self):
        if es_administrador(self.request.user):
            return IncidenciaAdminForm
        return IncidenciaResidenteForm

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user

        # Validación con django-rules a nivel de objeto
        if not user.has_perm('incidencias.editar_incidencia', obj) and not user.has_perm('incidencias.cambiar_estado', obj):
            raise PermissionDenied("No tienes permiso para modificar esta incidencia.")
        return obj

    def form_valid(self, form):
        incidencia_previa = Incidencia.objects.get(pk=self.object.pk)
        estado_anterior = incidencia_previa.estado
        tecnico_anterior = incidencia_previa.tecnico_asignado
        form.instance._actor_username = self.request.user.username

        # Sincronizar técnico y técnico asignado
        tecnico_obj = form.cleaned_data.get('tecnico')
        tecnico_asignado = form.cleaned_data.get('tecnico_asignado')
        if tecnico_obj and not tecnico_asignado:
            form.instance.tecnico_asignado = tecnico_obj.nombre
        elif tecnico_asignado and not tecnico_obj:
            form.instance.tecnico = Tecnico.objects.filter(nombre=tecnico_asignado).first()

        response = super().form_valid(form)

        # Auditoría de cambio de estado
        if self.object.estado != estado_anterior:
            tipo = 'reapertura' if (estado_anterior in ('resuelta', 'cerrada') and self.object.estado == 'proceso') else 'cambio_estado'
            EventoIncidencia.objects.create(
                incidencia=self.object,
                tipo=tipo,
                actor=self.request.user,
                estado_antes=estado_anterior,
                estado_despues=self.object.estado,
                detalle=f"Estado actualizado de {estado_anterior} a {self.object.estado}"
            )

        # Auditoría de asignación de técnico
        if self.object.tecnico_asignado != tecnico_anterior:
            disp_info = f" (Disponibilidad: {self.object.tecnico.get_disponibilidad_display()})" if self.object.tecnico else ""
            EventoIncidencia.objects.create(
                incidencia=self.object,
                tipo='asignacion',
                actor=self.request.user,
                detalle=f"Técnico asignado: '{self.object.tecnico_asignado}'{disp_info}"
            )

        messages.success(self.request, "Incidencia actualizada con éxito.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        es_admin = es_administrador(self.request.user)
        context['es_admin'] = es_admin
        if es_admin:
            context['titulo_accion'] = f"Gestionar Incidencia #{self.object.id} (Administración)"
        else:
            context['titulo_accion'] = f"Editar Mi Incidencia #{self.object.id}"
        return context


class IncidenciaDeleteView(LoginRequiredMixin, DeleteView):
    model = Incidencia
    template_name = 'incidencias/incidencia_confirm_delete.html'
    success_url = reverse_lazy('incidencia_list')

    def get_queryset(self):
        edificio = obtener_edificio_usuario(self.request)
        if self.request.user.is_superuser:
            return Incidencia.objects.all()
        if not edificio:
            return Incidencia.objects.none()
        return Incidencia.objects.del_edificio(edificio)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not self.request.user.has_perm('incidencias.eliminar_incidencia', obj):
            raise PermissionDenied("Solo el administrador del edificio puede eliminar incidencias.")
        return obj

    def delete(self, request, *args, **kwargs):
        messages.success(request, "La incidencia ha sido eliminada.")
        return super().delete(request, *args, **kwargs)


class DashboardAdminView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'incidencias/dashboard.html'

    def test_func(self):
        return es_administrador(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        edificio_usuario = obtener_edificio_usuario(self.request)
        user = self.request.user

        # Base inicial según rol y edificio activo
        if user.is_superuser:
            qs = Incidencia.objects.all()
            edificios_lista = list(Edificio.objects.all())
        elif edificio_usuario:
            qs = Incidencia.objects.del_edificio(edificio_usuario)
            edificios_lista = [edificio_usuario]
        else:
            qs = Incidencia.objects.none()
            edificios_lista = []

        # ── FILTROS M6: Edificio, Técnico, Rango de Fechas ──
        filtro_edificio = self.request.GET.get('edificio', '').strip()
        filtro_tecnico = self.request.GET.get('tecnico', '').strip()
        fecha_desde_str = self.request.GET.get('fecha_desde', '').strip()
        fecha_hasta_str = self.request.GET.get('fecha_hasta', '').strip()

        if filtro_edificio and (user.is_superuser or (edificio_usuario and str(edificio_usuario.pk) == filtro_edificio)):
            qs = qs.filter(edificio_id=filtro_edificio)

        if filtro_tecnico:
            if filtro_tecnico.isdigit():
                qs = qs.filter(Q(tecnico_id=int(filtro_tecnico)) | Q(tecnico_asignado__iexact=filtro_tecnico))
            else:
                qs = qs.filter(Q(tecnico_asignado__icontains=filtro_tecnico) | Q(tecnico__nombre__icontains=filtro_tecnico))

        if fecha_desde_str:
            f_desde = parse_date(fecha_desde_str)
            if f_desde:
                qs = qs.filter(fecha_creacion__date__gte=f_desde)

        if fecha_hasta_str:
            f_hasta = parse_date(fecha_hasta_str)
            if f_hasta:
                qs = qs.filter(fecha_creacion__date__lte=f_hasta)

        base_qs = qs.select_related('creador', 'edificio', 'tecnico')
        total_incidencias = base_qs.count()

        # ── LOS 4 INDICADORES OPERATIVOS DE M6 ──
        # 1. Tiempo Medio de Resolución (MTTR)
        resueltas = list(base_qs.filter(estado__in=['resuelta', 'cerrada']))
        total_resueltas = len(resueltas)

        if total_resueltas > 0:
            duraciones_segundos = [
                max((inc.fecha_actualizacion - inc.fecha_creacion).total_seconds(), 0)
                for inc in resueltas
            ]
            mttr_horas = round(sum(duraciones_segundos) / (total_resueltas * 3600), 1)
        else:
            mttr_horas = 0.0

        # 2. Cumplimiento de SLA (%)
        dentro_sla = 0
        fuera_sla = 0
        for inc in resueltas:
            duracion_horas = (inc.fecha_actualizacion - inc.fecha_creacion).total_seconds() / 3600
            sla_target = 4 if inc.prioridad == 'alta' else (24 if inc.prioridad == 'media' else 72)
            if duracion_horas <= sla_target:
                dentro_sla += 1
            else:
                fuera_sla += 1

        if total_resueltas > 0:
            cumplimiento_sla = round((dentro_sla / total_resueltas) * 100, 1)
        else:
            cumplimiento_sla = 100.0 if total_incidencias == 0 else 0.0

        # 3. Casos Abiertos Acumulados
        casos_abiertos_acumulados = base_qs.filter(estado__in=['pendiente', 'proceso']).count()

        # 4. Tasa de Reapertura (%)
        incidencias_reabiertas = EventoIncidencia.objects.filter(
            incidencia__in=base_qs,
            tipo='reapertura'
        ).values('incidencia_id').distinct().count()

        if total_incidencias > 0:
            tasa_reapertura = round((incidencias_reabiertas / total_incidencias) * 100, 1)
        else:
            tasa_reapertura = 0.0

        # Estadísticas para gráficos Chart.js
        por_categoria = list(base_qs.values('categoria').annotate(total=Count('id_incid')))
        nombres_cat = dict(Incidencia.CATEGORIAS)
        cat_labels = [nombres_cat.get(item['categoria'], item['categoria']) for item in por_categoria]
        cat_counts = [item['total'] for item in por_categoria]

        por_estado = list(base_qs.values('estado').annotate(total=Count('id_incid')))
        nombres_est = dict(Incidencia.ESTADOS)
        est_labels = [nombres_est.get(item['estado'], item['estado']) for item in por_estado]
        est_counts = [item['total'] for item in por_estado]

        por_prioridad = list(base_qs.values('prioridad').annotate(total=Count('id_incid')))
        nombres_prio = dict(Incidencia.PRIORIDADES)
        prio_labels = [nombres_prio.get(item['prioridad'], item['prioridad']) for item in por_prioridad]
        prio_counts = [item['total'] for item in por_prioridad]

        sla_labels = ['Dentro de SLA', 'Fuera de SLA']
        sla_counts = [dentro_sla, fuera_sla]

        # Carga por Técnico
        tecnicos_data = list(base_qs.exclude(tecnico_asignado__isnull=True).exclude(tecnico_asignado='').values('tecnico_asignado').annotate(total=Count('id_incid')).order_by('-total')[:6])
        tec_labels = [item['tecnico_asignado'] for item in tecnicos_data]
        tec_counts = [item['total'] for item in tecnicos_data]

        if user.is_superuser:
            total_edificios = Edificio.objects.count()
            total_residentes = Perfil.objects.count()
        elif edificio_usuario:
            total_edificios = 1
            total_residentes = Perfil.objects.filter(edificio=edificio_usuario).count()
        else:
            total_edificios = 0
            total_residentes = 0

        tecnicos_filtro_lista = Tecnico.objects.filter(activo=True)
        if not user.is_superuser and edificio_usuario:
            tecnicos_filtro_lista = tecnicos_filtro_lista.filter(Q(edificio=edificio_usuario) | Q(edificio__isnull=True))

        context.update({
            # 4 Indicadores M6
            'mttr_horas': mttr_horas,
            'cumplimiento_sla': cumplimiento_sla,
            'casos_abiertos_acumulados': casos_abiertos_acumulados,
            'tasa_reapertura': tasa_reapertura,
            'total_resueltas': total_resueltas,
            'dentro_sla': dentro_sla,
            'fuera_sla': fuera_sla,
            'incidencias_reabiertas': incidencias_reabiertas,

            # Filtros
            'filtro_edificio': filtro_edificio,
            'filtro_tecnico': filtro_tecnico,
            'filtro_fecha_desde': fecha_desde_str,
            'filtro_fecha_hasta': fecha_hasta_str,
            'edificios_lista': edificios_lista,
            'tecnicos_filtro_lista': tecnicos_filtro_lista,

            # JSONs para Chart.js
            'cat_labels_json': json.dumps(cat_labels),
            'cat_counts_json': json.dumps(cat_counts),
            'est_labels_json': json.dumps(est_labels),
            'est_counts_json': json.dumps(est_counts),
            'prio_labels_json': json.dumps(prio_labels),
            'prio_counts_json': json.dumps(prio_counts),
            'sla_labels_json': json.dumps(sla_labels),
            'sla_counts_json': json.dumps(sla_counts),
            'tec_labels_json': json.dumps(tec_labels),
            'tec_counts_json': json.dumps(tec_counts),

            'total_general': total_incidencias,
            'total_edificios': total_edificios,
            'total_residentes': total_residentes,
            'ultimas_incidencias': base_qs.order_by('-fecha_creacion')[:8],
            'edificio_activo': edificio_usuario,
        })
        return context


def incidencia_estado_live(request, pk):
    """
    Endpoint de tiempo real para residentes y administradores (M6).
    El residente ve el cambio de estado en pantalla en menos de 2 segundos sin recargar.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'No autenticado'}, status=401)

    edificio = obtener_edificio_usuario(request)
    if request.user.is_superuser:
        qs = Incidencia.objects.all()
    elif edificio:
        perfil = getattr(request.user, 'perfil', None)
        if perfil and perfil.rol in ('administrador', 'tecnico', 'auditor'):
            qs = Incidencia.objects.del_edificio(edificio)
        else:
            qs = Incidencia.objects.del_edificio(edificio).filter(creador=request.user)
    else:
        qs = Incidencia.objects.none()

    incidencia = get_object_or_404(qs, pk=pk)
    return JsonResponse({
        'id': incidencia.pk,
        'estado': incidencia.estado,
        'estado_display': incidencia.get_estado_display(),
        'prioridad': incidencia.prioridad,
        'prioridad_display': incidencia.get_prioridad_display(),
        'tecnico_asignado': incidencia.tecnico_asignado or 'Sin técnico asignado',
        'tecnico_disponibilidad': incidencia.tecnico.get_disponibilidad_display() if incidencia.tecnico else None,
        'version': incidencia.version,
        'fecha_actualizacion': incidencia.fecha_actualizacion.strftime('%d/%m/%Y %H:%M:%S'),
        'timestamp': incidencia.fecha_actualizacion.timestamp(),
    })


class TecnicoListView(LoginRequiredMixin, ListView):
    """
    Gestión de Técnicos para reparaciones y control de disponibilidad (M6).
    """
    model = Tecnico
    template_name = 'incidencias/tecnicos_list.html'
    context_object_name = 'tecnicos'

    def get_queryset(self):
        edificio = obtener_edificio_usuario(self.request)
        qs = Tecnico.objects.all().select_related('edificio')
        if not self.request.user.is_superuser and edificio:
            qs = qs.filter(Q(edificio=edificio) | Q(edificio__isnull=True))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = TecnicoForm()
        context['es_admin'] = es_administrador(self.request.user)
        base_qs = self.get_queryset()
        context['total_tecnicos'] = base_qs.count()
        context['total_disponibles'] = base_qs.filter(disponibilidad='disponible', activo=True).count()
        context['total_ocupados'] = base_qs.filter(disponibilidad='ocupado', activo=True).count()
        context['total_no_disponibles'] = base_qs.filter(disponibilidad__in=['descanso', 'no_disponible']).count()
        return context


def cambiar_disponibilidad_tecnico(request, pk):
    """Cambia rápidamente la disponibilidad de un técnico (M6)."""
    if not request.user.is_authenticated or not es_administrador(request.user):
        raise PermissionDenied("Solo administradores pueden cambiar la disponibilidad.")

    if request.method == 'POST':
        tecnico = get_object_or_404(Tecnico, pk=pk)
        nueva_disp = request.POST.get('disponibilidad')
        if nueva_disp in dict(Tecnico.DISPONIBILIDADES):
            tecnico.disponibilidad = nueva_disp
            tecnico.save(update_fields=['disponibilidad'])
            messages.success(request, f"Disponibilidad de {tecnico.nombre} actualizada a '{tecnico.get_disponibilidad_display()}'.")
        return redirect('tecnicos_list')
    return redirect('tecnicos_list')


class TecnicoCreateView(LoginRequiredMixin, CreateView):
    """Creación de un nuevo técnico en el catálogo."""
    model = Tecnico
    form_class = TecnicoForm
    template_name = 'incidencias/tecnico_form.html'
    success_url = reverse_lazy('tecnicos_list')

    def dispatch(self, request, *args, **kwargs):
        if not es_administrador(request.user):
            raise PermissionDenied("Solo administradores pueden registrar técnicos.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, f"Técnico '{form.instance.nombre}' creado exitosamente.")
        return super().form_valid(form)


class PerfilView(LoginRequiredMixin, TemplateView):
    template_name = 'incidencias/perfil.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        perfil = getattr(self.request.user, 'perfil', None)
        context['perfil'] = perfil
        context['es_admin'] = es_administrador(self.request.user)
        return context

def panel_observabilidad(request):
    if request.GET.get('reiniciar') == '1':
        reiniciar_observabilidad()
        return redirect('observabilidad')

    if request.GET.get('simular') == 'lenta':
        time.sleep(0.3)
        return redirect('observabilidad')

    if request.GET.get('simular') == 'error':
        return HttpResponseNotFound("Simulación de error 404 para pruebas de observabilidad.")
    
    contexto = obtener_estado_observabilidad()
    return render(request, 'incidencias/panel_observabilidad.html', contexto)