from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views

urlpatterns = [
    # Auth
    path('registro/', views.RegistroView.as_view(), name='registro'),
    path('login/', LoginView.as_view(template_name='incidencias/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('perfil/', views.PerfilView.as_view(), name='perfil'),

    # Incidencias CRUD
    path('', views.IncidenciaListView.as_view(), name='incidencia_list'),
    path('incidencias/nueva/', views.IncidenciaCreateView.as_view(), name='incidencia_create'),
    path('incidencias/<int:pk>/', views.IncidenciaDetailView.as_view(), name='incidencia_detail'),
    path('incidencias/<int:pk>/editar/', views.IncidenciaUpdateView.as_view(), name='incidencia_update'),
    path('incidencias/<int:pk>/eliminar/', views.IncidenciaDeleteView.as_view(), name='incidencia_delete'),

    # Tiempo real M6 (actualización en vivo para residentes y admin)
    path('incidencias/<int:pk>/estado-live/', views.incidencia_estado_live, name='incidencia_estado_live'),

    # Gestión de Técnicos y Disponibilidad (M6)
    path('tecnicos/', views.TecnicoListView.as_view(), name='tecnicos_list'),
    path('tecnicos/nuevo/', views.TecnicoCreateView.as_view(), name='tecnico_create'),
    path('tecnicos/<int:pk>/disponibilidad/', views.cambiar_disponibilidad_tecnico, name='tecnico_cambiar_disponibilidad'),

    # Bonus: Dashboard de métricas para Admin (M6 con 4 indicadores y filtros)
    path('dashboard/', views.DashboardAdminView.as_view(), name='dashboard'),

    # Observabilidad: Estado de trazas y métricas
    path('observabilidad/', views.panel_observabilidad, name='observabilidad'),
]
