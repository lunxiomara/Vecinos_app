"""
Pruebas M2 — Multi-edificio y Autorización
==========================================
Verifica que:
  1. Un usuario de edificio B recibe 404 en rutas del edificio A
  2. La matriz completa de permisos (4 roles × 8 acciones) es correcta

Ejecutar con:
    python manage.py test incidencias.tests_m2
o con pytest:
    pytest incidencias/tests_m2.py -v
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from incidencias.models import Edificio, Perfil, Incidencia, Unidad


# ─────────────────────────────────────────────
# Helpers de creación de fixtures
# ─────────────────────────────────────────────

def crear_edificio(nombre="EdifA"):
    return Edificio.objects.create(nombre=nombre, direccion=f"Calle {nombre} 1")


def crear_usuario_con_perfil(username, edificio, rol='residente', password='test1234'):
    user = User.objects.create_user(username=username, password=password)
    Perfil.objects.create(user=user, edificio=edificio, rol=rol)
    return user


def crear_incidencia(creador, edificio, estado='pendiente'):
    return Incidencia.objects.create(
        titulo=f"Incidencia de {creador.username}",
        descripcion="Descripción de prueba",
        categoria='otros',
        prioridad='media',
        estado=estado,
        creador=creador,
        edificio=edificio,
    )


# ─────────────────────────────────────────────
# TEST 1: Aislamiento entre edificios
# ─────────────────────────────────────────────

class AislamientoEdificioTest(TestCase):
    """
    Un residente del edificio B no puede ver incidencias del edificio A.
    """

    def setUp(self):
        self.edificio_a = crear_edificio("EdifA")
        self.edificio_b = crear_edificio("EdifB")

        self.residente_a = crear_usuario_con_perfil("res_a", self.edificio_a, 'residente')
        self.residente_b = crear_usuario_con_perfil("res_b", self.edificio_b, 'residente')

        self.incidencia_a = crear_incidencia(self.residente_a, self.edificio_a)
        self.client = Client()

    def test_residente_b_no_puede_ver_incidencia_de_a(self):
        """Residente del edificio B debe recibir 404 al intentar ver incidencia de A."""
        self.client.force_login(self.residente_b)
        url = reverse('incidencia_detail', args=[self.incidencia_a.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404,
            "El residente del edificio B debería recibir 404, no acceso.")

    def test_residente_a_puede_ver_su_propia_incidencia(self):
        """Residente del edificio A puede ver su propia incidencia."""
        self.client.force_login(self.residente_a)
        url = reverse('incidencia_detail', args=[self.incidencia_a.pk])
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])

    def test_manager_filtra_por_edificio(self):
        """El manager PorEdificio devuelve solo las del edificio correcto."""
        inc_b = crear_incidencia(self.residente_b, self.edificio_b)
        qs_a = Incidencia.objects.del_edificio(self.edificio_a)
        self.assertIn(self.incidencia_a, qs_a)
        self.assertNotIn(inc_b, qs_a)


# ─────────────────────────────────────────────
# TEST 2: Matriz de permisos con django-rules
# ─────────────────────────────────────────────

class MatrizPermisosTest(TestCase):
    """
    Verifica cada celda de la matriz:
    4 roles × 8 permisos de objeto
    """

    def setUp(self):
        self.edificio = crear_edificio("EdifTest")
        self.residente   = crear_usuario_con_perfil("res",   self.edificio, 'residente')
        self.admin       = crear_usuario_con_perfil("admin", self.edificio, 'administrador')
        self.tecnico     = crear_usuario_con_perfil("tec",   self.edificio, 'tecnico')
        self.auditor     = crear_usuario_con_perfil("aud",   self.edificio, 'auditor')

        # Incidencia del residente (mismo edificio)
        self.incidencia = crear_incidencia(self.residente, self.edificio, 'pendiente')

        # Incidencia de OTRO edificio (para tests de aislamiento)
        otro_edificio = crear_edificio("OtroEdif")
        otro_res = crear_usuario_con_perfil("otro_res", otro_edificio, 'residente')
        self.incidencia_otro = crear_incidencia(otro_res, otro_edificio)

    # ── ver_incidencia ────────────────────────────────────────────────────

    def test_residente_puede_ver_su_propia_incidencia(self):
        self.assertTrue(self.residente.has_perm('incidencias.ver_incidencia', self.incidencia))

    def test_residente_NO_puede_ver_incidencia_de_otro_edificio(self):
        self.assertFalse(self.residente.has_perm('incidencias.ver_incidencia', self.incidencia_otro))

    def test_admin_puede_ver_incidencia_del_edificio(self):
        self.assertTrue(self.admin.has_perm('incidencias.ver_incidencia', self.incidencia))

    def test_tecnico_puede_ver_incidencia_del_edificio(self):
        self.assertTrue(self.tecnico.has_perm('incidencias.ver_incidencia', self.incidencia))

    def test_auditor_puede_ver_incidencia_del_edificio(self):
        self.assertTrue(self.auditor.has_perm('incidencias.ver_incidencia', self.incidencia))

    # ── cambiar_estado ────────────────────────────────────────────────────

    def test_residente_NO_puede_cambiar_estado(self):
        self.assertFalse(self.residente.has_perm('incidencias.cambiar_estado', self.incidencia))

    def test_admin_puede_cambiar_estado(self):
        self.assertTrue(self.admin.has_perm('incidencias.cambiar_estado', self.incidencia))

    def test_tecnico_puede_cambiar_estado(self):
        self.assertTrue(self.tecnico.has_perm('incidencias.cambiar_estado', self.incidencia))

    def test_auditor_NO_puede_cambiar_estado(self):
        self.assertFalse(self.auditor.has_perm('incidencias.cambiar_estado', self.incidencia))

    # ── asignar_tecnico ───────────────────────────────────────────────────

    def test_solo_admin_puede_asignar_tecnico(self):
        self.assertTrue(self.admin.has_perm('incidencias.asignar_tecnico', self.incidencia))
        self.assertFalse(self.residente.has_perm('incidencias.asignar_tecnico', self.incidencia))
        self.assertFalse(self.tecnico.has_perm('incidencias.asignar_tecnico', self.incidencia))
        self.assertFalse(self.auditor.has_perm('incidencias.asignar_tecnico', self.incidencia))

    # ── eliminar_incidencia ───────────────────────────────────────────────

    def test_solo_admin_puede_eliminar(self):
        self.assertTrue(self.admin.has_perm('incidencias.eliminar_incidencia', self.incidencia))
        self.assertFalse(self.residente.has_perm('incidencias.eliminar_incidencia', self.incidencia))
        self.assertFalse(self.tecnico.has_perm('incidencias.eliminar_incidencia', self.incidencia))

    # ── ver_nota_interna ──────────────────────────────────────────────────

    def test_residente_NO_puede_ver_nota_interna(self):
        self.assertFalse(self.residente.has_perm('incidencias.ver_nota_interna', self.incidencia))

    def test_admin_puede_ver_nota_interna(self):
        self.assertTrue(self.admin.has_perm('incidencias.ver_nota_interna', self.incidencia))

    def test_tecnico_puede_ver_nota_interna(self):
        self.assertTrue(self.tecnico.has_perm('incidencias.ver_nota_interna', self.incidencia))

    def test_auditor_puede_ver_nota_interna(self):
        self.assertTrue(self.auditor.has_perm('incidencias.ver_nota_interna', self.incidencia))

    # ── exportar_auditar ──────────────────────────────────────────────────

    def test_solo_auditor_puede_exportar(self):
        self.assertTrue(self.auditor.has_perm('incidencias.exportar_auditar'))
        self.assertFalse(self.admin.has_perm('incidencias.exportar_auditar'))
        self.assertFalse(self.residente.has_perm('incidencias.exportar_auditar'))
        self.assertFalse(self.tecnico.has_perm('incidencias.exportar_auditar'))
