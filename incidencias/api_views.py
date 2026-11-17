"""
Vistas de API REST — Django REST Framework (M4)
==============================================
Implementa:
  1. Aislamiento multi-edificio en cada endpoint (404 si es de otro tenant).
  2. Idempotencia en POST con cabecera Idempotency-Key.
  3. Reutilización de los casos de uso de dominio (services.py).
  4. Documentación automática con drf-spectacular.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied, ValidationError
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from .models import Incidencia, Comentario, IdempotencyRecord
from .serializers import (
    IncidenciaListSerializer,
    IncidenciaDetailSerializer,
    IncidenciaCreateSerializer,
    CambiarEstadoSerializer,
    AsignarTecnicoSerializer,
    ComentarioSerializer
)
from .services import (
    cambiar_estado as service_cambiar_estado,
    asignar_tecnico as service_asignar_tecnico,
    ConcurrencyError,
    TransicionInvalidaError
)


class IdempotentCreateMixin:
    """
    Mixin que implementa soporte para cabecera Idempotency-Key.
    Si el cliente reintenta una petición con la misma clave, devuelve la
    respuesta almacenada previamente sin duplicar la creación en base de datos.
    """
    def create(self, request, *args, **kwargs):
        idempotency_key = request.headers.get('Idempotency-Key') or request.META.get('HTTP_IDEMPOTENCY_KEY')

        if idempotency_key:
            registro_existente = IdempotencyRecord.objects.filter(
                key=idempotency_key,
                user=request.user,
                path=request.path
            ).first()

            if registro_existente:
                response = Response(
                    registro_existente.response_body,
                    status=registro_existente.status_code
                )
                response['X-Idempotent-Replay'] = 'true'
                return response

        # Ejecución normal de la creación
        response = super().create(request, *args, **kwargs)

        if idempotency_key and status.is_success(response.status_code):
            IdempotencyRecord.objects.create(
                key=idempotency_key,
                user=request.user,
                method='POST',
                path=request.path,
                status_code=response.status_code,
                response_body=response.data
            )
            response['X-Idempotent-Replay'] = 'false'

        return response


class IncidenciaViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """
    ViewSet para gestión de incidencias con aislamiento multi-inquilino.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        edificio = getattr(self.request, 'edificio_activo', None)
        if not edificio and hasattr(user, 'perfil'):
            edificio = user.perfil.edificio

        if user.is_superuser:
            return Incidencia.objects.all().select_related('creador', 'creador__perfil', 'edificio')

        if not edificio:
            return Incidencia.objects.none()

        perfil = getattr(user, 'perfil', None)
        if perfil and perfil.rol in ('administrador', 'tecnico', 'auditor'):
            return Incidencia.objects.del_edificio(edificio).select_related('creador', 'creador__perfil', 'edificio')

        # Residente: solo sus propias incidencias en su edificio
        return Incidencia.objects.del_edificio(edificio).filter(creador=user).select_related('creador', 'creador__perfil', 'edificio')

    def get_serializer_class(self):
        if self.action == 'list':
            return IncidenciaListSerializer
        if self.action == 'create':
            return IncidenciaCreateSerializer
        return IncidenciaDetailSerializer

    @extend_schema(
        request=CambiarEstadoSerializer,
        responses={200: IncidenciaDetailSerializer},
        description="Avanza o reabre el estado de una incidencia utilizando la máquina de estados con bloqueo pesimista."
    )
    @action(detail=True, methods=['post'], url_path='cambiar-estado')
    def cambiar_estado(self, request, pk=None):
        incidencia = self.get_object()
        user = request.user

        if not user.has_perm('incidencias.cambiar_estado', incidencia):
            return Response(
                {"detail": "No tienes permiso para cambiar el estado de esta incidencia."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CambiarEstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            incidencia_actualizada = service_cambiar_estado(
                incidencia_id=incidencia.id,
                nuevo_estado=serializer.validated_data['nuevo_estado'],
                actor=user,
                detalle=serializer.validated_data.get('detalle', ''),
                version_esperada=serializer.validated_data.get('version_esperada')
            )
            return Response(IncidenciaDetailSerializer(incidencia_actualizada).data)
        except ConcurrencyError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except TransicionInvalidaError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=AsignarTecnicoSerializer,
        responses={200: IncidenciaDetailSerializer},
        description="Asigna un técnico responsable a la incidencia bajo bloqueo select_for_update."
    )
    @action(detail=True, methods=['post'], url_path='asignar-tecnico')
    def asignar_tecnico(self, request, pk=None):
        incidencia = self.get_object()
        user = request.user

        if not user.has_perm('incidencias.asignar_tecnico', incidencia):
            return Response(
                {"detail": "Solo el administrador de este edificio puede asignar técnicos."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = AsignarTecnicoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            incidencia_actualizada = service_asignar_tecnico(
                incidencia_id=incidencia.id,
                nombre_tecnico=serializer.validated_data['nombre_tecnico'],
                actor=user,
                version_esperada=serializer.validated_data.get('version_esperada')
            )
            return Response(IncidenciaDetailSerializer(incidencia_actualizada).data)
        except ConcurrencyError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)


class ComentarioViewSet(viewsets.ModelViewSet):
    """ViewSet para comentarios de incidencias."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ComentarioSerializer

    def get_queryset(self):
        user = self.request.user
        edificio = getattr(self.request, 'edificio_activo', None)
        if not edificio and hasattr(user, 'perfil'):
            edificio = user.perfil.edificio

        if user.is_superuser:
            return Comentario.objects.all().select_related('autor', 'incidencia')

        if not edificio:
            return Comentario.objects.none()

        return Comentario.objects.del_edificio(edificio).select_related('autor', 'incidencia')
