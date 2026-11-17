"""
Rutas de la API REST v1 — Vecinos App (M4)
=========================================
Endpoints versionados bajo /api/v1/
Incluye documentación interactiva Swagger UI y Redoc.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from .api_views import IncidenciaViewSet, ComentarioViewSet


router = DefaultRouter()
router.register(r'incidencias', IncidenciaViewSet, basename='api_incidencia')
router.register(r'comentarios', ComentarioViewSet, basename='api_comentario')

urlpatterns = [
    # ── Autenticación JWT ──────────────────────────────────────
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ── Documentación OpenAPI 3.0 / Swagger / Redoc ───────────
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # ── Recursos REST ──────────────────────────────────────────
    path('', include(router.urls)),
]
