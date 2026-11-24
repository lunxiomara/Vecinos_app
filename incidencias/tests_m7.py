from django.contrib.auth.models import User
from django.test import TestCase
import rules

from incidencias.models import (
    Edificio,
    Incidencia,
    OutboxMessage,
    Perfil,
    Unidad,
)


class DominioReglasYModelosM7Tests(TestCase):
    def setUp(self):
        self.edif_a = Edificio.objects.create(nombre="Torre Norte", direccion="Calle 100 # 10-20")
        self.edif_b = Edificio.objects.create(nombre="Torre Sur", direccion="Carrera 15 # 50-30")
        self.unidad_a = Unidad.objects.create(edificio=self.edif_a, numero="101", piso="1")

        self.residente = User.objects.create_user(username="res_a", password="123")
        Perfil.objects.create(
            user=self.residente,
            edificio=self.edif_a,
            unidad=self.unidad_a,
            rol="residente",
        )

        self.otro_residente = User.objects.create_user(username="res_a2", password="123")
        Perfil.objects.create(
            user=self.otro_residente,
            edificio=self.edif_a,
            rol="residente",
        )

        self.admin = User.objects.create_user(username="adm_a", password="123")
        Perfil.objects.create(user=self.admin, edificio=self.edif_a, rol="administrador")

        self.tecnico = User.objects.create_user(username="tec_a", password="123")
        Perfil.objects.create(user=self.tecnico, edificio=self.edif_a, rol="tecnico")

        self.auditor = User.objects.create_user(username="aud_a", password="123")
        Perfil.objects.create(user=self.auditor, edificio=self.edif_a, rol="auditor")

        self.user_sin_perfil = User.objects.create_user(username="sin_perfil", password="123")

        self.inc_pendiente = Incidencia.objects.create(
            edificio=self.edif_a,
            creador=self.residente,
            titulo="Fuga en baño",
            descripcion="Goteo constante",
            categoria="agua",
            prioridad="media",
            estado="pendiente",
        )

    def test_helpers_de_rol_en_perfil(self):
        self.assertTrue(self.residente.perfil.es_residente)
        self.assertFalse(self.residente.perfil.puede_gestionar)
        self.assertTrue(self.admin.perfil.es_administrador)
        self.assertTrue(self.admin.perfil.puede_gestionar)
        self.assertTrue(self.tecnico.perfil.es_tecnico)
        self.assertTrue(self.tecnico.perfil.puede_gestionar)
        self.assertTrue(self.auditor.perfil.es_auditor)
        self.assertFalse(self.auditor.perfil.puede_gestionar)

    def test_permisos_matriz_por_rol_y_edificio(self):
        self.assertTrue(rules.has_perm("incidencias.crear_incidencia", self.residente))
        self.assertTrue(rules.has_perm("incidencias.crear_incidencia", self.admin))
        self.assertFalse(rules.has_perm("incidencias.crear_incidencia", self.tecnico))
        self.assertFalse(rules.has_perm("incidencias.crear_incidencia", self.auditor))
        self.assertFalse(rules.has_perm("incidencias.crear_incidencia", self.user_sin_perfil))

        self.assertTrue(rules.has_perm("incidencias.ver_incidencia", self.residente, self.inc_pendiente))
        self.assertFalse(rules.has_perm("incidencias.ver_incidencia", self.otro_residente, self.inc_pendiente))
        self.assertTrue(rules.has_perm("incidencias.ver_incidencia", self.tecnico, self.inc_pendiente))
        self.assertTrue(rules.has_perm("incidencias.ver_incidencia", self.auditor, self.inc_pendiente))

        self.assertTrue(rules.has_perm("incidencias.editar_incidencia", self.residente, self.inc_pendiente))
        self.assertFalse(rules.has_perm("incidencias.editar_incidencia", self.otro_residente, self.inc_pendiente))
        self.assertTrue(rules.has_perm("incidencias.editar_incidencia", self.admin, self.inc_pendiente))

        self.inc_pendiente.estado = "proceso"
        self.inc_pendiente.save()
        self.assertFalse(rules.has_perm("incidencias.editar_incidencia", self.residente, self.inc_pendiente))
        self.assertTrue(rules.has_perm("incidencias.cambiar_estado", self.tecnico, self.inc_pendiente))
        self.assertFalse(rules.has_perm("incidencias.asignar_tecnico", self.tecnico, self.inc_pendiente))
        self.assertTrue(rules.has_perm("incidencias.asignar_tecnico", self.admin, self.inc_pendiente))
        self.assertTrue(rules.has_perm("incidencias.ver_nota_interna", self.auditor, self.inc_pendiente))
        self.assertTrue(rules.has_perm("incidencias.exportar_auditar", self.auditor))
        self.assertFalse(rules.has_perm("incidencias.exportar_auditar", self.admin))

    def test_maquina_de_estados_incidencia(self):
        inc = Incidencia(estado="pendiente")
        self.assertTrue(inc.puede_transicionar_a("proceso"))
        self.assertFalse(inc.puede_transicionar_a("resuelta"))
        self.assertFalse(inc.puede_transicionar_a("cerrada"))

        inc.estado = "proceso"
        self.assertTrue(inc.puede_transicionar_a("resuelta"))
        self.assertTrue(inc.puede_transicionar_a("pendiente"))

        inc.estado = "resuelta"
        self.assertTrue(inc.puede_transicionar_a("cerrada"))
        self.assertTrue(inc.puede_transicionar_a("proceso"))

        inc.estado = "cerrada"
        self.assertFalse(inc.puede_transicionar_a("proceso"))
        self.assertFalse(inc.puede_transicionar_a("pendiente"))

    def test_manager_filtra_por_edificio_y_abiertas(self):
        inc_b = Incidencia.objects.create(
            edificio=self.edif_b,
            creador=self.admin,
            titulo="Corte de luz",
            descripcion="Tablero general",
            categoria="electricidad",
            prioridad="alta",
            estado="pendiente",
        )
        inc_cerrada = Incidencia.objects.create(
            edificio=self.edif_a,
            creador=self.admin,
            titulo="Aseo pasillo",
            descripcion="Completado",
            categoria="limpieza",
            prioridad="baja",
            estado="cerrada",
        )

        qs_a = Incidencia.objects.del_edificio(self.edif_a)
        self.assertIn(self.inc_pendiente, qs_a)
        self.assertIn(inc_cerrada, qs_a)
        self.assertNotIn(inc_b, qs_a)

        abiertas_a = Incidencia.objects.abiertas_del_edificio(self.edif_a)
        self.assertIn(self.inc_pendiente, abiertas_a)
        self.assertNotIn(inc_cerrada, abiertas_a)

    def test_outbox_message_creacion_y_str(self):
        msg = OutboxMessage.objects.create(
            tipo_evento="INCIDENCIA_CREADA",
            payload={"id_incid": self.inc_pendiente.pk},
        )
        self.assertEqual(msg.estado, "PENDING")
        self.assertIn("INCIDENCIA_CREADA", str(msg))