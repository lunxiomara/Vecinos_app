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

    # Bonus: Dashboard de métricas para Admin
    path('dashboard/', views.DashboardAdminView.as_view(), name='dashboard'),
]
