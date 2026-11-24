"""
Capa de Casos de Uso / Servicios de Dominio (M1 & M3)
===================================================
Aisla las reglas de negocio de las vistas de Django.
Maneja transacciones atómicas, auditoría inmutable y control
de concurrencia pesimista (select_for_update) y optimista (campo version).
"""

from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Incidencia, EventoIncidencia, OutboxMessage


class ConcurrencyError(Exception):
    """Lanzada cuando ocurre un conflicto de bloqueo optimista."""
    pass


class TransicionInvalidaError(ValidationError):
    """Lanzada cuando se intenta una transición de estado no permitida."""
    pass


def asignar_tecnico(incidencia_id: int, nombre_tecnico: str, actor, version_esperada: int = None) -> Incidencia:
    """
    Caso de uso: Asignación concurrente segura de técnico.
    
    Aplica BLOQUEO PESIMISTA con select_for_update():
    Garantiza que una incidencia NUNCA quede con dos técnicos ni sufra
    condiciones de carrera cuando múltiples administradores la editan al mismo tiempo.
    """
    with transaction.atomic():
        # Bloqueo a nivel de fila en la base de datos (Pessimistic Lock)
        incidencia = Incidencia.objects.select_for_update().get(id_incid=incidencia_id)

        # Control de concurrencia optimista opcional
        if version_esperada is not None and incidencia.version != version_esperada:
            raise ConcurrencyError(
                f"Conflicto de concurrencia en Incidencia #{incidencia_id}: "
                f"versión esperada {version_esperada}, pero la actual es {incidencia.version}."
            )

        tecnico_anterior = incidencia.tecnico_asignado
        incidencia.tecnico_asignado = nombre_tecnico
        incidencia.version += 1
        incidencia._actor_username = getattr(actor, 'username', 'sistema')
        incidencia.save(update_fields=['tecnico_asignado', 'version', 'fecha_actualizacion'])

        # Registro inmutable de auditoría
        EventoIncidencia.objects.create(
            incidencia=incidencia,
            tipo='asignacion',
            actor=actor,
            detalle=f"Técnico asignado por {getattr(actor, 'username', 'sistema')}: '{nombre_tecnico}' (antes: '{tecnico_anterior or 'Sin asignar'}')"
        )

        return incidencia


def cambiar_estado(incidencia_id: int, nuevo_estado: str, actor, detalle: str = '', version_esperada: int = None) -> Incidencia:
    with transaction.atomic():
        incidencia = Incidencia.objects.select_for_update().get(id_incid=incidencia_id)

        if version_esperada is not None and incidencia.version != version_esperada:
            raise ConcurrencyError(
                f"La incidencia #{incidencia_id} fue modificada por otro usuario mientras la editabas."
            )

        if not incidencia.puede_transicionar_a(nuevo_estado):
            raise TransicionInvalidaError(
                f"Transición inválida: no se puede pasar de '{incidencia.estado}' a '{nuevo_estado}'."
            )

        estado_anterior = incidencia.estado
        tipo_evento = 'reapertura' if (estado_anterior in ('resuelta', 'cerrada') and nuevo_estado == 'proceso') else 'cambio_estado'

        incidencia.estado = nuevo_estado
        incidencia.version += 1
        incidencia._actor_username = getattr(actor, 'username', 'sistema')
        incidencia.save(update_fields=['estado', 'version', 'fecha_actualizacion'])

        EventoIncidencia.objects.create(
            incidencia=incidencia,
            tipo=tipo_evento,
            actor=actor,
            estado_antes=estado_anterior,
            estado_despues=nuevo_estado,
            detalle=detalle or f"Cambio de estado de {estado_anterior} a {nuevo_estado}"
        )

        return incidencia

    
def reabrir_incidencia(incidencia_id: int, actor, motivo: str) -> Incidencia:
    """Caso de uso específico para reapertura de incidencias resueltas."""
    return cambiar_estado(
        incidencia_id=incidencia_id,
        nuevo_estado='proceso',
        actor=actor,
        detalle=f"Incidencia reabierta: {motivo}"
    )
