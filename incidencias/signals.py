import uuid

from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Incidencia, OutboxMessage


@receiver(pre_save, sender=Incidencia)
def registrar_estado_previo(sender, instance, using, update_fields=None, **kwargs):
    if update_fields is not None and 'estado' not in update_fields:
        instance._estado_previo = None
        return
    if instance.pk:
        try:
            prev_instance = Incidencia.objects.using(using).get(pk=instance.pk)
            instance._estado_previo = prev_instance.estado
        except Incidencia.DoesNotExist:
            instance._estado_previo = None
    else:
        instance._estado_previo = None


@receiver(post_save, sender=Incidencia)
def encolar_notificacion_cambio_estado(sender, instance, created, using, update_fields=None, **kwargs):
    estado_previo = getattr(instance, '_estado_previo', None)
    if created or estado_previo is None or estado_previo == instance.estado:
        return
    if update_fields is not None and 'estado' not in update_fields:
        return

    creador = instance.creador
    payload = {
        'incidencia_id': instance.pk,
        'titulo': instance.titulo,
        'estado_anterior': estado_previo,
        'estado_nuevo': instance.estado,
        'estado_nuevo_display': instance.get_estado_display(),
        'tecnico_asignado': instance.tecnico_asignado or '',
        'actor': getattr(instance, '_actor_username', 'sistema'),
        'destinatario': creador.email,
        'nombre_destinatario': creador.first_name or creador.username,
    }
    message = OutboxMessage.objects.using(using).create(
        tipo_evento='incidencia.estado_cambiado',
        payload=payload,
        dedupe_key=f"incidencia:{instance.pk}:estado:{uuid.uuid4()}",
    )

    from .tasks import enqueue_outbox_message
    transaction.on_commit(lambda: enqueue_outbox_message(message.pk), using=using)