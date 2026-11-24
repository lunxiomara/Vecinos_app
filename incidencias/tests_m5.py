from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from incidencias.models import Edificio, Incidencia, OutboxMessage, Perfil
from incidencias.services import cambiar_estado
from incidencias.tasks import check_sla_breaches, dispatch_outbox_message


class OutboxTransaccionalTests(TestCase):
    def setUp(self):
        self.edificio = Edificio.objects.create(
            nombre="Torre M5",
            direccion="Calle 5",
        )
        self.admin = User.objects.create_user(
            username="admin_m5",
            password="ClaveSegura123!",
            email="admin@example.com",
        )
        Perfil.objects.create(
            user=self.admin,
            edificio=self.edificio,
            rol="administrador",
        )
        self.residente = User.objects.create_user(
            username="residente_m5",
            password="ClaveSegura123!",
            email="residente@example.com",
        )
        Perfil.objects.create(
            user=self.residente,
            edificio=self.edificio,
            rol="residente",
        )
        self.incidencia = Incidencia.objects.create(
            edificio=self.edificio,
            creador=self.residente,
            titulo="Fuga de agua en cocina",
            descripcion="La tubería presenta una fuga.",
            estado="pendiente",
        )

    def test_cambio_de_estado_y_outbox_se_guardan_en_la_misma_transaccion(self):
        with patch("incidencias.tasks.dispatch_outbox_message.delay") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                cambiar_estado(
                    incidencia_id=self.incidencia.pk,
                    nuevo_estado="proceso",
                    actor=self.admin,
                )

        message = OutboxMessage.objects.filter(tipo_evento="incidencia.estado_cambiado").order_by("-pk").first()
        self.assertIsNotNone(message)
        self.incidencia.refresh_from_db()
        self.assertEqual(self.incidencia.estado, "proceso")
        self.assertEqual(message.tipo_evento, "incidencia.estado_cambiado")
        self.assertEqual(message.payload["estado_anterior"], "pendiente")
        self.assertEqual(message.payload["estado_nuevo"], "proceso")
        enqueue.assert_called_once_with(message.pk)

    def test_al_revertir_la_transaccion_no_queda_evento_outbox(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                cambiar_estado(
                    incidencia_id=self.incidencia.pk,
                    nuevo_estado="proceso",
                    actor=self.admin,
                )
                raise RuntimeError("rollback de prueba")

        self.incidencia.refresh_from_db()
        self.assertEqual(self.incidencia.estado, "pendiente")
        self.assertFalse(OutboxMessage.objects.exists())

    def test_procesar_dos_veces_un_mensaje_no_repite_la_entrega(self):
        message = OutboxMessage.objects.create(
            tipo_evento="incidencia.estado_cambiado",
            payload={
                "incidencia_id": self.incidencia.pk,
                "titulo": self.incidencia.titulo,
                "estado_anterior": "pendiente",
                "estado_nuevo": "proceso",
                "estado_nuevo_display": "En Proceso",
                "destinatario": self.residente.email,
                "nombre_destinatario": self.residente.username,
            },
        )
        with patch("incidencias.tasks._deliver_email") as send_email:
            with patch("incidencias.tasks._deliver_webhook"):
                dispatch_outbox_message.apply(args=(message.pk,), throw=True)
                dispatch_outbox_message.apply(args=(message.pk,), throw=True)

        message.refresh_from_db()
        self.assertEqual(message.estado, "PROCESSED")
        self.assertEqual(message.intentos, 1)
        send_email.assert_called_once()

    def test_error_de_entrega_programa_reintento_con_backoff(self):
        message = OutboxMessage.objects.create(
            tipo_evento="incidencia.estado_cambiado",
            payload={
                "incidencia_id": self.incidencia.pk,
                "titulo": self.incidencia.titulo,
                "estado_anterior": "pendiente",
                "estado_nuevo": "proceso",
                "estado_nuevo_display": "En Proceso",
                "destinatario": self.residente.email,
            },
        )
        before = timezone.now()
        with patch("incidencias.tasks._deliver_webhook"):
            with patch("incidencias.tasks._deliver_email", side_effect=RuntimeError("SMTP caído")):
                dispatch_outbox_message.apply(args=(message.pk,), throw=False)

        message.refresh_from_db()
        self.assertEqual(message.estado, "PENDING")
        self.assertEqual(message.intentos, 1)
        self.assertEqual(message.ultimo_error, "SMTP caído")
        self.assertGreaterEqual(
            message.proximo_reintento,
            before + timedelta(seconds=59),
        )

    def test_alerta_sla_se_crea_una_sola_vez_por_incidencia(self):
        Incidencia.objects.filter(pk=self.incidencia.pk).update(
            fecha_creacion=timezone.now() - timedelta(hours=25),
        )

        with patch("incidencias.tasks.dispatch_outbox_message.delay"):
            check_sla_breaches.apply(args=(), throw=True)
            check_sla_breaches.apply(args=(), throw=True)

        alerts = OutboxMessage.objects.filter(tipo_evento="incidencia.sla_vencido")
        self.assertEqual(alerts.count(), 1)
        self.assertEqual(
            alerts.get().dedupe_key,
            f"sla:{self.incidencia.pk}:24",
        )