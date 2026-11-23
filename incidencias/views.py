import json
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.models import Group
from django.contrib import messages
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.http import Http404

from .models import Incidencia, Comentario, Perfil, Edificio, EventoIncidencia
from .forms import RegistroForm, IncidenciaResidenteForm, IncidenciaAdminForm, ComentarioForm
from .filters import IncidenciaFilter


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
            EventoIncidencia.objects.create(
                incidencia=self.object,
                tipo='asignacion',
                actor=self.request.user,
                detalle=f"Técnico asignado: {self.object.tecnico_asignado}"
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
        edificio = obtener_edificio_usuario(self.request)

        # Aislamiento en el panel: admin solo ve su propio edificio (salvo superuser)
        if self.request.user.is_superuser:
            base_qs = Incidencia.objects.all()
            total_edificios = Edificio.objects.count()
            total_residentes = Perfil.objects.count()
        elif edificio:
            base_qs = Incidencia.objects.del_edificio(edificio)
            total_edificios = 1
            total_residentes = Perfil.objects.filter(edificio=edificio).count()
        else:
            base_qs = Incidencia.objects.none()
            total_edificios = 0
            total_residentes = 0

        # Estadísticas por Categoría
        por_categoria = list(base_qs.values('categoria').annotate(total=Count('id_incid')))
        nombres_cat = dict(Incidencia.CATEGORIAS)
        cat_labels = [nombres_cat.get(item['categoria'], item['categoria']) for item in por_categoria]
        cat_counts = [item['total'] for item in por_categoria]

        # Estadísticas por Estado
        por_estado = list(base_qs.values('estado').annotate(total=Count('id_incid')))
        nombres_est = dict(Incidencia.ESTADOS)
        est_labels = [nombres_est.get(item['estado'], item['estado']) for item in por_estado]
        est_counts = [item['total'] for item in por_estado]

        # Estadísticas por Prioridad
        por_prioridad = list(base_qs.values('prioridad').annotate(total=Count('id_incid')))
        nombres_prio = dict(Incidencia.PRIORIDADES)
        prio_labels = [nombres_prio.get(item['prioridad'], item['prioridad']) for item in por_prioridad]
        prio_counts = [item['total'] for item in por_prioridad]

        context.update({
            'cat_labels_json': json.dumps(cat_labels),
            'cat_counts_json': json.dumps(cat_counts),
            'est_labels_json': json.dumps(est_labels),
            'est_counts_json': json.dumps(est_counts),
            'prio_labels_json': json.dumps(prio_labels),
            'prio_counts_json': json.dumps(prio_counts),
            'total_general': base_qs.count(),
            'total_edificios': total_edificios,
            'total_residentes': total_residentes,
            'ultimas_incidencias': base_qs.select_related('creador').order_by('-fecha_creacion')[:5],
            'edificio_activo': edificio,
        })
        return context


class PerfilView(LoginRequiredMixin, TemplateView):
    template_name = 'incidencias/perfil.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        perfil = getattr(self.request.user, 'perfil', None)
        context['perfil'] = perfil
        context['es_admin'] = es_administrador(self.request.user)
        return context
