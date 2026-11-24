from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Edificio, EventoIncidencia, Incidencia, Perfil, Unidad
from .observabilidad import reiniciar_observabilidad


class DominioIncidenciasTestCase(TestCase):
    def setUp(self):
        self.edificio_a = Edificio.objects.create(
            nombre="Torre Norte",
            direccion="Calle 100 # 15-20",
        )
        self.edificio_b = Edificio.objects.create(
            nombre="Torre Sur",
            direccion="Carrera 7 # 45-10",
        )
        self.unidad_a1 = Unidad.objects.create(
            edificio=self.edificio_a,
            numero="101",
            piso="1",
        )
        self.unidad_b1 = Unidad.objects.create(
            edificio=self.edificio_b,
            numero="201",
            piso="2",
        )

        self.usuario_residente = User.objects.create_user(
            username="residente_a",
            password="Password123!",
        )
        self.perfil_residente = Perfil.objects.create(
            user=self.usuario_residente,
            edificio=self.edificio_a,
            unidad=self.unidad_a1,
            rol="residente",
        )

        self.usuario_admin = User.objects.create_user(
            username="admin_a",
            password="Password123!",
        )
        self.perfil_admin = Perfil.objects.create(
            user=self.usuario_admin,
            edificio=self.edificio_a,
            rol="administrador",
        )

        self.incidencia_a_abierta = Incidencia.objects.create(
            edificio=self.edificio_a,
            creador=self.usuario_residente,
            titulo="Fuga de agua en tubería principal",
            descripcion="Se presenta filtración constante en la zona común.",
            categoria="agua",
            prioridad="alta",
            estado="pendiente",
        )
        self.incidencia_a_cerrada = Incidencia.objects.create(
            edificio=self.edificio_a,
            creador=self.usuario_residente,
            titulo="Luminaria dañada en pasillo",
            descripcion="Bombillo fundido en el acceso del piso.",
            categoria="electricidad",
            prioridad="baja",
            estado="cerrada",
        )
        self.incidencia_b = Incidencia.objects.create(
            edificio=self.edificio_b,
            creador=self.usuario_admin,
            titulo="Portón principal con fallo",
            descripcion="El motor del portón no abre con normalidad.",
            categoria="seguridad",
            prioridad="media",
            estado="proceso",
        )

    def test_transiciones_validas_maquina_estados(self):
        incidencia = Incidencia(estado="pendiente")
        self.assertTrue(incidencia.puede_transicionar_a("proceso"))
        self.assertFalse(incidencia.puede_transicionar_a("resuelta"))
        self.assertFalse(incidencia.puede_transicionar_a("cerrada"))

        incidencia.estado = "proceso"
        self.assertTrue(incidencia.puede_transicionar_a("resuelta"))
        self.assertTrue(incidencia.puede_transicionar_a("pendiente"))
        self.assertFalse(incidencia.puede_transicionar_a("cerrada"))

        incidencia.estado = "resuelta"
        self.assertTrue(incidencia.puede_transicionar_a("cerrada"))
        self.assertTrue(incidencia.puede_transicionar_a("proceso"))

        incidencia.estado = "cerrada"
        self.assertFalse(incidencia.puede_transicionar_a("pendiente"))
        self.assertFalse(incidencia.puede_transicionar_a("proceso"))
        self.assertFalse(incidencia.puede_transicionar_a("resuelta"))

    def test_manager_aisla_incidencias_por_edificio(self):
        qs_a = Incidencia.objects.del_edificio(self.edificio_a)
        qs_b = Incidencia.objects.del_edificio(self.edificio_b)

        self.assertIn(self.incidencia_a_abierta, qs_a)
        self.assertIn(self.incidencia_a_cerrada, qs_a)
        self.assertNotIn(self.incidencia_b, qs_a)

        self.assertIn(self.incidencia_b, qs_b)
        self.assertNotIn(self.incidencia_a_abierta, qs_b)

    def test_manager_abiertas_del_edificio_excluye_resuelta_y_cerrada(self):
        abiertas_a = Incidencia.objects.abiertas_del_edificio(self.edificio_a)
        self.assertIn(self.incidencia_a_abierta, abiertas_a)
        self.assertNotIn(self.incidencia_a_cerrada, abiertas_a)

    def test_roles_perfil_y_permiso_gestion(self):
        self.assertTrue(self.perfil_residente.es_residente)
        self.assertFalse(self.perfil_residente.puede_gestionar)

        self.assertTrue(self.perfil_admin.es_administrador)
        self.assertTrue(self.perfil_admin.puede_gestionar)

    def test_creacion_evento_incidencia_auditoria(self):
        evento = EventoIncidencia.objects.create(
            incidencia=self.incidencia_a_abierta,
            tipo="creacion",
            actor=self.usuario_residente,
            estado_despues="pendiente",
            detalle="Creación inicial de prueba",
        )
        self.assertEqual(evento.incidencia, self.incidencia_a_abierta)
        self.assertEqual(evento.tipo, "creacion")
        self.assertEqual(evento.estado_despues, "pendiente")


class ObservabilidadTestCase(TestCase):
    def setUp(self):
        reiniciar_observabilidad()
        self.client = Client()

    def tearDown(self):
        reiniciar_observabilidad()

    def test_panel_observabilidad_carga_y_registra_peticion(self):
        self.client.get(reverse("login"))
        url = reverse("observabilidad")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("metricas", response.context)
        self.assertGreaterEqual(response.context["metricas"]["total_peticiones"], 1)

    def test_simulacion_error_dispara_alerta(self):
        url = reverse("observabilidad")
        response_error = self.client.get("/ruta-inexistente-404/")
        self.assertEqual(response_error.status_code, 404)

        response_panel = self.client.get(url)
        self.assertEqual(response_panel.status_code, 200)
        self.assertTrue(response_panel.context["alerta_activa"])
        self.assertGreaterEqual(response_panel.context["metricas"]["alertas_disparadas"], 1)

    def test_reiniciar_observabilidad(self):
        self.client.get("/ruta-inexistente-404/")
        url = reverse("observabilidad")
        response_reset = self.client.get(f"{url}?reiniciar=1")
        self.assertEqual(response_reset.status_code, 302)

        response_panel = self.client.get(url)
        self.assertFalse(response_panel.context["alerta_activa"])
        self.assertEqual(response_panel.context["metricas"]["alertas_disparadas"], 0)