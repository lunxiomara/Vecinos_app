"""
Pruebas M6 — Tiempo Real, Panel de Indicadores y Gestión de Técnicos
====================================================================
Criterio de aceptación M6:
  - El residente ve el cambio de estado en menos de 2 segundos sin recargar (endpoint live).
  - El panel responde con los 4 indicadores operativos (MTTR, Cumplimiento de SLA,
    Casos Abiertos Acumulados, Tasa de Reapertura) y filtros por edificio, técnico y fechas.
  - Catálogo de técnicos para arreglos con asignación por disponibilidad.
"""

from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from incidencias.models import Edificio, Perfil, Incidencia, EventoIncidencia, Tecnico
from incidencias.services import cambiar_estado, asignar_tecnico, reabrir_incidencia


class TiempoRealM6Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.edificio_a = Edificio.objects.create(nombre="Edificio Norte", direccion="Calle 100 #10-20")
        self.edificio_b = Edificio.objects.create(nombre="Edificio Sur", direccion="Carrera 50 #30-40")

        # Residente Edificio A
        self.residente_a = User.objects.create_user(username="residente_a", password="password123")
        Perfil.objects.create(user=self.residente_a, edificio=self.edificio_a, rol="residente")

        # Residente Edificio B
        self.residente_b = User.objects.create_user(username="residente_b", password="password123")
        Perfil.objects.create(user=self.residente_b, edificio=self.edificio_b, rol="residente")

        # Admin Edificio A
        self.admin_a = User.objects.create_user(username="admin_a", password="password123", is_staff=True)
        Perfil.objects.create(user=self.admin_a, edificio=self.edificio_a, rol="administrador")

        # Técnico
        self.tecnico = Tecnico.objects.create(
            nombre="Carlos Fontanero",
            especialidad="plomeria",
            disponibilidad="disponible",
            edificio=self.edificio_a
        )

        # Incidencia en Edificio A
        self.incidencia = Incidencia.objects.create(
            titulo="Fuga en tubería principal",
            descripcion="El agua se está filtrando al pasillo",
            categoria="agua",
            prioridad="alta",
            estado="pendiente",
            creador=self.residente_a,
            edificio=self.edificio_a,
        )

    def test_endpoint_live_devuelve_estado_actual_en_json(self):
        self.client.force_login(self.residente_a)
        url = reverse('incidencia_estado_live', kwargs={'pk': self.incidencia.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['id'], self.incidencia.pk)
        self.assertEqual(data['estado'], 'pendiente')
        self.assertEqual(data['estado_display'], 'Pendiente')

    def test_cambio_de_estado_se_refleja_inmediatamente_en_tiempo_real(self):
        """Verifica el criterio: el residente ve el cambio sin recargar la página."""
        self.client.force_login(self.residente_a)
        url = reverse('incidencia_estado_live', kwargs={'pk': self.incidencia.pk})

        # Inicialmente pendiente
        res1 = self.client.get(url).json()
        self.assertEqual(res1['estado'], 'pendiente')

        # Admin pasa la incidencia a 'proceso' y asigna técnico
        cambiar_estado(incidencia_id=self.incidencia.pk, nuevo_estado='proceso', actor=self.admin_a)
        asignar_tecnico(incidencia_id=self.incidencia.pk, actor=self.admin_a, tecnico_id=self.tecnico.pk)

        # La consulta del residente refleja el cambio inmediatamente (< 2s)
        res2 = self.client.get(url).json()
        self.assertEqual(res2['estado'], 'proceso')
        self.assertEqual(res2['tecnico_asignado'], 'Carlos Fontanero')

    def test_aislamiento_residente_otro_edificio_recibe_404_en_endpoint_live(self):
        """Mantiene el aislamiento estricto de M2 en las rutas de tiempo real."""
        self.client.force_login(self.residente_b)
        url = reverse('incidencia_estado_live', kwargs={'pk': self.incidencia.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class PanelIndicadoresM6Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.edificio = Edificio.objects.create(nombre="Torre Central", direccion="Av. 68 #80")
        self.admin = User.objects.create_user(username="admin_central", password="password123", is_staff=True)
        Perfil.objects.create(user=self.admin, edificio=self.edificio, rol="administrador")

        self.residente = User.objects.create_user(username="residente_1", password="password123")
        Perfil.objects.create(user=self.residente, edificio=self.edificio, rol="residente")

        self.tecnico_1 = Tecnico.objects.create(
            nombre="Andrés Electricista",
            especialidad="electricidad",
            disponibilidad="disponible",
            edificio=self.edificio
        )

        ahora = timezone.now()

        # Incidencia 1: Resuelta en 2 horas (Dentro de SLA de alta=4h)
        self.inc1 = Incidencia.objects.create(
            titulo="Cortocircuito en tablero",
            descripcion="Chispas en caja de fusibles",
            categoria="electricidad",
            prioridad="alta",
            estado="resuelta",
            creador=self.residente,
            edificio=self.edificio,
            tecnico=self.tecnico_1,
            tecnico_asignado=self.tecnico_1.nombre,
        )
        # Ajustamos timestamps para simular 2 horas
        Incidencia.objects.filter(pk=self.inc1.pk).update(
            fecha_creacion=ahora - timedelta(hours=5),
            fecha_actualizacion=ahora - timedelta(hours=3),
        )

        # Incidencia 2: Resuelta en 30 horas (Fuera de SLA de media=24h)
        self.inc2 = Incidencia.objects.create(
            titulo="Cerradura rota en puerta",
            descripcion="No abre la puerta comunitaria",
            categoria="seguridad",
            prioridad="media",
            estado="cerrada",
            creador=self.residente,
            edificio=self.edificio,
            tecnico=self.tecnico_1,
            tecnico_asignado=self.tecnico_1.nombre,
        )
        Incidencia.objects.filter(pk=self.inc2.pk).update(
            fecha_creacion=ahora - timedelta(hours=40),
            fecha_actualizacion=ahora - timedelta(hours=10),
        )

        # Incidencia 3: Abierta (pendiente)
        self.inc3 = Incidencia.objects.create(
            titulo="Bombillo fundido pasillo",
            descripcion="Pasillo oscuro",
            categoria="electricidad",
            prioridad="baja",
            estado="pendiente",
            creador=self.residente,
            edificio=self.edificio,
        )

        # Incidencia 4: Abierta (en proceso) y con reapertura previa
        self.inc4 = Incidencia.objects.create(
            titulo="Fuga persistente en baño",
            descripcion="Volvió a gotear tras reparación",
            categoria="agua",
            prioridad="media",
            estado="proceso",
            creador=self.residente,
            edificio=self.edificio,
        )
        EventoIncidencia.objects.create(
            incidencia=self.inc4,
            tipo="reapertura",
            actor=self.admin,
            detalle="Reabierta por reporte de goteo recurrente"
        )

    def test_dashboard_calcula_los_cuatro_indicadores_m6(self):
        self.client.force_login(self.admin)
        url = reverse('dashboard')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        ctx = response.context

        # 1. MTTR: promedio de (2h + 30h) / 2 = 16.0 horas
        self.assertAlmostEqual(ctx['mttr_horas'], 16.0, delta=0.5)

        # 2. Cumplimiento SLA: 1 de 2 resueltas dentro de SLA -> 50.0%
        self.assertEqual(ctx['cumplimiento_sla'], 50.0)

        # 3. Casos abiertos acumulados: inc3 (pendiente) + inc4 (proceso) = 2
        self.assertEqual(ctx['casos_abiertos_acumulados'], 2)

        # 4. Tasa de reapertura: 1 de 4 incidencias tuvo reapertura -> 25.0%
        self.assertEqual(ctx['tasa_reapertura'], 25.0)

    def test_dashboard_filtros_por_tecnico_y_fechas(self):
        self.client.force_login(self.admin)
        url = reverse('dashboard')

        # Filtrar por técnico "Andrés Electricista"
        response = self.client.get(url, {'tecnico': 'Andrés Electricista'})
        self.assertEqual(response.status_code, 200)
        # inc1 y inc2 tienen a Andrés Electricista
        self.assertEqual(response.context['total_general'], 2)

        # Filtrar por fecha hoy
        hoy = timezone.now().date().strftime('%Y-%m-%d')
        response_hoy = self.client.get(url, {'fecha_desde': hoy, 'fecha_hasta': hoy})
        self.assertEqual(response_hoy.status_code, 200)


class TecnicosYDisponibilidadTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.edificio = Edificio.objects.create(nombre="Edificio Palmas", direccion="Calle 1 #2-3")
        self.admin = User.objects.create_user(username="admin_palmas", password="password123", is_staff=True)
        Perfil.objects.create(user=self.admin, edificio=self.edificio, rol="administrador")

        self.residente = User.objects.create_user(username="residente_palmas", password="password123")
        Perfil.objects.create(user=self.residente, edificio=self.edificio, rol="residente")

    def test_creacion_y_listado_de_tecnico_con_disponibilidad(self):
        self.client.force_login(self.admin)

        # Registrar técnico
        url_crear = reverse('tecnico_create')
        data = {
            'nombre': 'Luis Martínez',
            'especialidad': 'plomeria',
            'disponibilidad': 'disponible',
            'telefono': '3001112233',
            'email': 'luis@plomeros.com',
            'edificio': self.edificio.pk,
            'activo': True,
        }
        res_post = self.client.post(url_crear, data)
        self.assertEqual(res_post.status_code, 302)

        tecnico = Tecnico.objects.get(nombre="Luis Martínez")
        self.assertTrue(tecnico.esta_disponible)
        self.assertEqual(tecnico.disponibilidad, 'disponible')

    def test_cambiar_disponibilidad_tecnico(self):
        self.client.force_login(self.admin)
        tecnico = Tecnico.objects.create(
            nombre="Javier Cerrajería",
            especialidad="seguridad",
            disponibilidad="disponible",
            edificio=self.edificio
        )

        url_cambio = reverse('tecnico_cambiar_disponibilidad', kwargs={'pk': tecnico.pk})
        res = self.client.post(url_cambio, {'disponibilidad': 'ocupado'})
        self.assertEqual(res.status_code, 302)

        tecnico.refresh_from_db()
        self.assertEqual(tecnico.disponibilidad, 'ocupado')
        self.assertFalse(tecnico.esta_disponible)

    def test_asignacion_de_tecnico_a_incidencia(self):
        tecnico = Tecnico.objects.create(
            nombre="Roberto Gas",
            especialidad="gas",
            disponibilidad="disponible",
            edificio=self.edificio
        )
        incidencia = Incidencia.objects.create(
            titulo="Olor a gas en calentador",
            descripcion="Revisar válvula",
            categoria="otros",
            prioridad="alta",
            creador=self.residente,
            edificio=self.edificio,
        )

        inc_actualizada = asignar_tecnico(
            incidencia_id=incidencia.pk,
            actor=self.admin,
            tecnico_id=tecnico.pk
        )

        self.assertEqual(inc_actualizada.tecnico, tecnico)
        self.assertEqual(inc_actualizada.tecnico_asignado, "Roberto Gas")

        # Verificar evento inmutable registrado
        evento = EventoIncidencia.objects.filter(incidencia=incidencia, tipo="asignacion").first()
        self.assertIsNotNone(evento)
        self.assertIn("Roberto Gas", evento.detalle)
        self.assertIn("Disponible", evento.detalle)
