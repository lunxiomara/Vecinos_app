from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import Incidencia

@receiver(pre_save, sender=Incidencia)
def registrar_estado_previo(sender, instance, **kwargs):
    """Guarda el estado anterior antes de guardar para detectar cambios."""
    if instance.pk:
        try:
            prev_instance = Incidencia.objects.get(pk=instance.pk)
            instance._estado_previo = prev_instance.estado
        except Incidencia.DoesNotExist:
            instance._estado_previo = None
    else:
        instance._estado_previo = None

@receiver(post_save, sender=Incidencia)
def notificar_cambio_estado(sender, instance, created, **kwargs):
    """Envía un correo al residente cuando su incidencia cambia de estado o se resuelve."""
    if not created and hasattr(instance, '_estado_previo'):
        if instance._estado_previo != instance.estado:
            creador = instance.creador
            if creador.email:
                asunto = f"[VecinosApp] Tu incidencia ha sido actualizada: #{instance.id} - {instance.titulo}"
                mensaje = (
                    f"Hola {creador.first_name or creador.username},\n\n"
                    f"Te informamos que tu incidencia '{instance.titulo}' ha cambiado de estado:\n"
                    f"Estado anterior: {instance._estado_previo.capitalize()}\n"
                    f"Nuevo estado: {instance.get_estado_display()}\n\n"
                )
                if instance.estado == 'resuelta':
                    mensaje += "¡Tu incidencia ha sido marcada como RESUELTA por el administrador!\n\n"
                if instance.tecnico_asignado:
                    mensaje += f"Técnico asignado: {instance.tecnico_asignado}\n"
                
                mensaje += "Puedes revisar los detalles y comentarios en la plataforma.\n\nSaludos,\nEquipo VecinosApp"

                send_mail(
                    subject=asunto,
                    message=mensaje,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[creador.email],
                    fail_silently=True,
                )
