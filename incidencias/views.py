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

from .models import Incidencia, Comentario, Perfil, Edificio
from .forms import RegistroForm, IncidenciaResidenteForm, IncidenciaAdminForm, ComentarioForm
from .filters import IncidenciaFilter

def es_administrador(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff or user.groups.filter(name='Administrador').exists())

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
        if es_administrador(user):
            qs = Incidencia.objects.all().select_related('creador', 'creador__perfil', 'creador__perfil__edificio')
        else:
            qs = Incidencia.objects.filter(creador=user).select_related('creador')
        
        self.filterset = IncidenciaFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        context['es_admin'] = es_administrador(self.request.user)
        # Resumen rápido de estados
        base_qs = Incidencia.objects.all() if es_administrador(self.request.user) else Incidencia.objects.filter(creador=self.request.user)
        context['total_incidencias'] = base_qs.count()
        context['total_pendientes'] = base_qs.filter(estado='pendiente').count()
        context['total_proceso'] = base_qs.filter(estado='proceso').count()
        context['total_resueltas'] = base_qs.filter(estado='resuelta').count()
        context['total_cerradas'] = base_qs.filter(estado='cerrada').count()
        return context

class IncidenciaDetailView(LoginRequiredMixin, DetailView):
    model = Incidencia
    template_name = 'incidencias/incidencia_detail.html'
    context_object_name = 'incidencia'

    def get_queryset(self):
        user = self.request.user
        if es_administrador(user):
            return Incidencia.objects.all().select_related('creador', 'creador__perfil')
        return Incidencia.objects.filter(creador=user).select_related('creador', 'creador__perfil')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comentarios'] = self.object.comentarios.all().select_related('autor')
        context['comentario_form'] = ComentarioForm()
        context['es_admin'] = es_administrador(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Validación estricta de permisos para comentar
        if not es_administrador(request.user) and self.object.creador != request.user:
            raise PermissionDenied("Solo el administrador o el residente creador pueden añadir comentarios a esta incidencia.")

        form = ComentarioForm(request.POST)
        if form.is_valid():
            comentario = form.save(commit=False)
            comentario.incidencia = self.object
            comentario.autor = request.user
            comentario.save()
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
        if es_administrador(request.user):
            messages.warning(request, "Los administradores no reportan incidencias; su rol es gestionar y resolver las incidencias reportadas por los residentes.")
            return redirect('incidencia_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.creador = self.request.user
        form.instance.estado = 'pendiente'
        messages.success(self.request, "Incidencia reportada con éxito. Será revisada por la administración.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo_accion'] = "Reportar Nueva Incidencia"
        return context

class IncidenciaUpdateView(LoginRequiredMixin, UpdateView):
    model = Incidencia
    template_name = 'incidencias/incidencia_form.html'
    success_url = reverse_lazy('incidencia_list')

    def get_form_class(self):
        if es_administrador(self.request.user):
            return IncidenciaAdminForm
        return IncidenciaResidenteForm

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user
        if not es_administrador(user):
            if obj.creador != user:
                raise PermissionDenied("No tienes permiso para editar esta incidencia.")
            if not obj.puede_editar_residente:
                messages.error(self.request, "No puedes modificar una incidencia que ya está en proceso o resuelta.")
                raise PermissionDenied("Solo puedes editar incidencias en estado Pendiente.")
        return obj

    def form_valid(self, form):
        messages.success(self.request, "Incidencia actualizada con éxito.")
        return super().form_valid(form)

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

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user
        if not es_administrador(user) and obj.creador != user:
            raise PermissionDenied("Solo el administrador o el creador de la incidencia pueden eliminarla.")
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
        # Estadísticas por Categoría
        por_categoria = list(Incidencia.objects.values('categoria').annotate(total=Count('id')))
        # Mapear nombres legibles
        nombres_cat = dict(Incidencia.CATEGORIAS)
        cat_labels = [nombres_cat.get(item['categoria'], item['categoria']) for item in por_categoria]
        cat_counts = [item['total'] for item in por_categoria]

        # Estadísticas por Estado
        por_estado = list(Incidencia.objects.values('estado').annotate(total=Count('id')))
        nombres_est = dict(Incidencia.ESTADOS)
        est_labels = [nombres_est.get(item['estado'], item['estado']) for item in por_estado]
        est_counts = [item['total'] for item in por_estado]

        # Estadísticas por Prioridad
        por_prioridad = list(Incidencia.objects.values('prioridad').annotate(total=Count('id')))
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
            'total_general': Incidencia.objects.count(),
            'total_edificios': Edificio.objects.count(),
            'total_residentes': Perfil.objects.count(),
            'ultimas_incidencias': Incidencia.objects.select_related('creador').order_by('-fecha_creacion')[:5]
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
