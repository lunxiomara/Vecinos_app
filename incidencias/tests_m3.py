"""
Pruebas Automatizadas M3 — Rendimiento, Erradicación de N+1 y Concurrencia
========================================================================
Criterios de Aceptación:
  1. Cero consultas N+1 (verificado con assertNumQueries).
  2. Concurrencia protegida: 20 hilos simultáneos asignando técnico sobre
     la misma incidencia no provocan corrupción de datos ni estados inconsistentes.
  3. Control de versiones optimista (campo version y ConcurrencyError).
  4. Transiciones de estado validadas por el caso de uso.

Uso:
    python manage.py test incidencias.tests_m3
"""

import threading
from django.test import TransactionTestCase, TestCase
from django.contrib.auth.models import User
from django.db import connection

from incidencias.models import Edificio, Perfil, Incidencia, EventoIncidencia
from incidencias.services import (
    asignar_tecnico,
    cambiar_estado,
    ConcurrencyError,
    TransicionInvalidaError
)


# ─────────────────────────────────────────────
# 1. TEST DE PREVENCIÓN DE CONSULTAS N+1
# ─────────────────────────────────────────────

class OptimizacionConsultasNPlusOneTest(TestCase):
    """Verifica que las consultas usen select_related/prefetch y no caigan en N+1."""

    def setUp(self):
        self.edificio = Edificio.objects.create(nombre="Torre Test N+1", direccion="Cl 1")
        self.creador = User.objects.create_user(username="residente_n1", password="pw")
        Perfil.objects.create(user=self.creador, edificio=self.edificio, rol='residente')

        # Creamos 20 incidencias
        incidencias = [
            Incidencia(
                edificio=self.edificio,
                creador=self.creador,
                titulo=f"Incidencia #{i}",
                descripcion="Detalle",
                categoria='otros',
                prioridad='media',
                estado='pendiente'
            )
            for i in range(20)
        ]
        Incidencia.objects.bulk_create(incidencias)

    def test_listado_no_tiene_consultas_n_mas_uno(self):
        """
        Al listar 20 incidencias y acceder al edificio y creador,
        DEBE realizarse exactamente 1 sola consulta SQL con JOIN, nunca 21 consultas.
        """
        with self.assertNumQueries(1):
            qs = list(
                Incidencia.objects.del_edificio(self.edificio)
                .select_related('creador', 'creador__perfil', 'edificio')[:20]
            )
            # Accedemos a los campos de relaciones en memoria
            for inc in qs:
                _ = inc.creador.username
                _ = inc.creador.perfil.rol
                _ = inc.edificio.nombre

            self.assertEqual(len(qs), 20)


# ─────────────────────────────────────────────
# 2. TEST DE CONCURRENCIA ESTRESADA (20 HILOS)
# ─────────────────────────────────────────────

class ConcurrenciaSelectForUpdateTest(TransactionTestCase):
    """
    Prueba de estrés multihilo:
    Lanza 20 hilos simultáneos asignando técnico sobre la MISMA incidencia.
    Usa TransactionTestCase para permitir transacciones reales entre hilos.
    """

    def setUp(self):
        self.edificio = Edificio.objects.create(nombre="Torre Concurrencia", direccion="Cl 2")
        self.admin = User.objects.create_user(username="admin_hilos", password="pw")
        Perfil.objects.create(user=self.admin, edificio=self.edificio, rol='administrador')

        self.incidencia = Incidencia.objects.create(
            edificio=self.edificio,
            creador=self.admin,
            titulo="Fuga crítica concurrente",
            descripcion="Prueba multihilo",
            categoria='agua',
            prioridad='alta',
            estado='pendiente',
            version=1
        )

    def test_veinte_hilos_asignando_tecnico_concurrente(self):
        """
        20 hilos compiten por asignar técnicos diferentes.
        El bloqueo pesimista select_for_update serializa la fila.
        Resultado: versión = 21, 20 eventos inmutables registrados, y la fila es íntegra.
        """
        num_hilos = 20
        barrera = threading.Barrier(num_hilos)  # Sincroniza inicio exacto
        errores = []

        def worker(thread_idx):
            connection.close()  # Conexión propia de base de datos por hilo
            try:
                barrera.wait(timeout=5)  # Espera a que los 20 hilos estén listos
                nombre_tecnico = f"Técnico_HILO_{thread_idx}"
                asignar_tecnico(
                    incidencia_id=self.incidencia.id_incid,
                    nombre_tecnico=nombre_tecnico,
                    actor=self.admin
                )
            except Exception as e:
                errores.append(e)

        hilos = [threading.Thread(target=worker, args=(i,)) for i in range(num_hilos)]

        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=10)

        self.assertEqual(len(errores), 0, f"Ocurrieron errores en los hilos: {errores}")

        # Verificación post-concurrencia
        self.incidencia.refresh_from_db()
        # La versión inicial era 1, con 20 asignaciones debe ser 21
        self.assertEqual(self.incidencia.version, 1 + num_hilos)
        # Deben existir exactamente 20 eventos de auditoría inmutables
        eventos = EventoIncidencia.objects.filter(incidencia=self.incidencia, tipo='asignacion').count()
        self.assertEqual(eventos, num_hilos)


# ─────────────────────────────────────────────
# 3. TEST DE BLOQUEO OPTIMISTA Y TRANSICIONES
# ─────────────────────────────────────────────

class BloqueoOptimistaYTransicionesTest(TestCase):
    """Verifica detección de colisiones optimistas y máquina de estados."""

    def setUp(self):
        self.edificio = Edificio.objects.create(nombre="Torre Maquina Estados", direccion="Cl 3")
        self.user = User.objects.create_user(username="test_transicion", password="pw")
        Perfil.objects.create(user=self.user, edificio=self.edificio, rol='administrador')

        self.incidencia = Incidencia.objects.create(
            edificio=self.edificio,
            creador=self.user,
            titulo="Incidencia Estado",
            descripcion="Test",
            estado='pendiente',
            version=1
        )

    def test_bloqueo_optimista_detecta_version_desactualizada(self):
        """Si se pasa una versión antigua, se levanta ConcurrencyError."""
        # Simulamos que otro usuario modificó la versión primero a 2
        self.incidencia.version = 2
        self.incidencia.save(update_fields=['version'])

        # Usuario A intenta guardar creyendo que la versión era 1
        with self.assertRaises(ConcurrencyError):
            cambiar_estado(
                incidencia_id=self.incidencia.id_incid,
                nuevo_estado='proceso',
                actor=self.user,
                version_esperada=1  # Ya no es 1
            )

    def test_transicion_invalida_es_rechazada(self):
        """No se puede saltar directamente de pendiente a cerrada."""
        with self.assertRaises(TransicionInvalidaError):
            cambiar_estado(
                incidencia_id=self.incidencia.id_incid,
                nuevo_estado='cerrada',  # Invalido desde pendiente
                actor=self.user
            )

    def test_transicion_valida_actualiza_version_y_auditoria(self):
        """Transición válida: pendiente -> proceso."""
        inc = cambiar_estado(
            incidencia_id=self.incidencia.id_incid,
            nuevo_estado='proceso',
            actor=self.user
        )
        self.assertEqual(inc.estado, 'proceso')
        self.assertEqual(inc.version, 2)
        evento = EventoIncidencia.objects.filter(incidencia=inc, tipo='cambio_estado').first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.estado_antes, 'pendiente')
        self.assertEqual(evento.estado_despues, 'proceso')