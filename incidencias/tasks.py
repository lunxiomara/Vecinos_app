import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import timedelta
from urllib.request import Request, urlopen

from celery import shared_task
from kombu.exceptions import OperationalError
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Incidencia, OutboxMessage, Perfil

logger = logging.getLogger(__name__)
OUTBOX_LEASE_SECONDS = 300
OUTBOX_BATCH_SIZE = 100


def enqueue_outbox_message(message_id):
    try:
        dispatch_outbox_message.delay(message_id)
    except OperationalError:
        logger.exception(
            "No se pudo publicar el mensaje outbox %s; el barrido periódico lo recuperará.",
            message_id,
        )


def _record_channel_delivery(message_id, lease_token, payload, channel):
    with transaction.atomic():
        message = OutboxMessage.objects.select_for_update().get(pk=message_id)
        if message.estado != 'PROCESSING' or message.lease_token != lease_token:
            raise RuntimeError(f"Se perdió la reserva del mensaje outbox {message_id}.")
        delivered_channels = list(message.payload.get('_delivered_channels', []))
        if channel not in delivered_channels:
            delivered_channels.append(channel)
            message.payload['_delivered_channels'] = delivered_channels
            message.save(update_fields=['payload'])
        payload['_delivered_channels'] = delivered_channels


def _deliver_email(message_id, payload):
    recipients = payload.get('destinatarios')
    if recipients is None:
        recipient = payload.get('destinatario')
        recipients = [recipient] if recipient else []
    if not recipients:
        return

    subject = payload.get('asunto')
    body = payload.get('mensaje')
    if subject is None or body is None:
        subject = f"[VecinosApp] Actualización de incidencia #{payload['incidencia_id']}"
        body = (
            f"Hola {payload.get('nombre_destinatario') or 'residente'},\n\n"
            f"Tu incidencia '{payload['titulo']}' cambió de "
            f"{payload['estado_anterior']} a {payload['estado_nuevo_display']}.\n"
        )
        if payload.get('tecnico_asignado'):
            body += f"Técnico asignado: {payload['tecnico_asignado']}\n"
        body += "\nEquipo VecinosApp"

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        headers={'Message-ID': f'<vecinos-outbox-{message_id}@vecinosapp>'},
    )
    if email.send(fail_silently=False) != 1:
        raise RuntimeError(f"No se pudo enviar el correo del mensaje outbox {message_id}.")


def _deliver_webhook(message_id, event_type, payload):
    url = os.environ.get('VECINOS_WEBHOOK_URL')
    if not url:
        return

    secret = os.environ.get('VECINOS_WEBHOOK_SECRET')
    if not secret:
        raise RuntimeError('VECINOS_WEBHOOK_SECRET es obligatorio al configurar VECINOS_WEBHOOK_URL.')

    body = json.dumps(
        {'id': message_id, 'event': event_type, 'payload': payload},
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode('utf-8'),
        timestamp.encode('ascii') + b'.' + body,
        hashlib.sha256,
    ).hexdigest()
    request = Request(
        url,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'X-Vecinos-Event': event_type,
            'X-Vecinos-Timestamp': timestamp,
            'X-Vecinos-Signature': f'sha256={signature}',
            'Idempotency-Key': str(message_id),
        },
        method='POST',
    )
    with urlopen(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"El webhook respondió con HTTP {response.status}.")


@shared_task(bind=True, max_retries=None, name='incidencias.dispatch_outbox_message')
def dispatch_outbox_message(self, message_id):
    """Reclama un evento persistido, entrega los canales y reintenta con backoff."""
    now = timezone.now()
    with transaction.atomic():
        message = OutboxMessage.objects.select_for_update().get(pk=message_id)
        if message.estado in ('PROCESSED', 'FAILED'):
            return message.estado
        if message.proximo_reintento > now:
            return message.estado

        lease_token = str(uuid.uuid4())
        message.estado = 'PROCESSING'
        message.intentos += 1
        message.lease_token = lease_token
        message.proximo_reintento = now + timedelta(seconds=OUTBOX_LEASE_SECONDS)
        message.save(update_fields=[
            'estado', 'intentos', 'lease_token', 'proximo_reintento',
        ])
        event_type = message.tipo_evento
        payload = message.payload
        attempt = message.intentos
        max_attempts = message.max_intentos

    try:
        delivered_channels = payload.get('_delivered_channels', [])
        if 'webhook' not in delivered_channels:
            _deliver_webhook(message_id, event_type, payload)
            _record_channel_delivery(message_id, lease_token, payload, 'webhook')
        if 'email' not in delivered_channels:
            _deliver_email(message_id, payload)
            _record_channel_delivery(message_id, lease_token, payload, 'email')
    except Exception as error:
        retry_delay = min(3600, 60 * (2 ** (attempt - 1)))
        with transaction.atomic():
            message = OutboxMessage.objects.select_for_update().get(pk=message_id)
            if message.estado != 'PROCESSING' or message.lease_token != lease_token:
                logger.warning("Se descartó un fallo tardío del mensaje outbox %s.", message_id)
                return message.estado
            message.ultimo_error = str(error)
            message.lease_token = ''
            if attempt >= max_attempts:
                message.estado = 'FAILED'
                message.proximo_reintento = now
            else:
                message.estado = 'PENDING'
                message.proximo_reintento = timezone.now() + timedelta(seconds=retry_delay)
            message.save(update_fields=[
                'estado', 'ultimo_error', 'lease_token', 'proximo_reintento',
            ])

        logger.exception("Falló la entrega del mensaje outbox %s.", message_id)
        if attempt >= max_attempts:
            raise
        raise self.retry(exc=error, countdown=retry_delay)

    with transaction.atomic():
        message = OutboxMessage.objects.select_for_update().get(pk=message_id)
        if message.estado == 'PROCESSING' and message.lease_token == lease_token:
            message.estado = 'PROCESSED'
            message.procesado_en = timezone.now()
            message.ultimo_error = ''
            message.lease_token = ''
            message.save(update_fields=[
                'estado', 'procesado_en', 'ultimo_error', 'lease_token',
            ])
    return 'PROCESSED'


@shared_task(name='incidencias.requeue_pending_outbox')
def requeue_pending_outbox():
    """Recupera mensajes pendientes si el broker o el worker estaban fuera de servicio."""
    now = timezone.now()
    due_messages = OutboxMessage.objects.filter(
        Q(estado='PENDING', proximo_reintento__lte=now)
        | Q(estado='PROCESSING', proximo_reintento__lte=now)
    ).order_by('creado_en').values_list('pk', flat=True)[:OUTBOX_BATCH_SIZE]
    message_ids = list(due_messages)
    for message_id in message_ids:
        enqueue_outbox_message(message_id)
    return len(message_ids)


@shared_task(name='incidencias.check_sla_breaches')
def check_sla_breaches():
    """Crea una alerta única para cada incidencia abierta que exceda el SLA."""
    sla_hours = settings.VECINOS_SLA_HOURS
    deadline = timezone.now() - timedelta(hours=sla_hours)
    incidents = Incidencia.objects.filter(
        estado__in=('pendiente', 'proceso'),
        fecha_creacion__lte=deadline,
    ).select_related('edificio')

    created_count = 0
    for incident in incidents.iterator():
        recipients = list(
            Perfil.objects.filter(
                edificio=incident.edificio,
                rol='administrador',
                user__email__gt='',
            ).values_list('user__email', flat=True)
        )
        message, created = OutboxMessage.objects.get_or_create(
            dedupe_key=f'sla:{incident.pk}:{sla_hours}',
            defaults={
                'tipo_evento': 'incidencia.sla_vencido',
                'payload': {
                    'incidencia_id': incident.pk,
                    'titulo': incident.titulo,
                    'edificio': incident.edificio.nombre if incident.edificio else '',
                    'estado': incident.get_estado_display(),
                    'destinatarios': recipients,
                    'asunto': f"[VecinosApp] SLA vencido: incidencia #{incident.pk}",
                    'mensaje': (
                        f"La incidencia '{incident.titulo}' del edificio "
                        f"'{incident.edificio}' lleva más de {sla_hours} horas abierta."
                    ),
                },
            },
        )
        if created:
            created_count += 1
            transaction.on_commit(
                lambda message_id=message.pk: enqueue_outbox_message(message_id)
            )
    return created_count
