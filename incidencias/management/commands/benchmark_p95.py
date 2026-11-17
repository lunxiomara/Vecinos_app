"""
Comando de Medición de Rendimiento p95 y Análisis de EXPLAIN (M3)
===============================================================
Mide la latencia percentil 95 (p95) sobre consultas de listado, búsqueda y panel.
Imprime el plan de ejecución SQL (EXPLAIN) para verificar uso de índices compuestos.

Uso:
    python manage.py benchmark_p95
"""

import time
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count
from incidencias.models import Incidencia, Edificio


class Command(BaseCommand):
    help = "Calcula el percentil p95 de latencia e inspecciona planes EXPLAIN en base de datos"

    def add_arguments(self, parser):
        parser.add_argument('--iteraciones', type=int, default=100, help='Número de iteraciones para medir')

    def handle(self, *args, **options):
        iteraciones = options['iteraciones']
        total_incidencias = Incidencia.objects.count()

        self.stdout.write(self.style.NOTICE(f"\n========================================================"))
        self.stdout.write(self.style.NOTICE(f"   BENCHMARK DE RENDIMIENTO (M3) — {total_incidencias:,} INCIDENCIAS"))
        self.stdout.write(self.style.NOTICE(f"========================================================\n"))

        edificio = Edificio.objects.first()
        if not edificio:
            self.stdout.write(self.style.ERROR("No se encontró ningún edificio. Ejecuta primero: python manage.py seed_incidencias"))
            return

        # ── 1. BENCHMARK LISTADO CON ÍNDICE COMPUESTO ──────────────
        latencias_listado = []
        for _ in range(iteraciones):
            t0 = time.perf_counter()
            # Consulta típica de paginación del residente / admin
            list(Incidencia.objects.del_edificio(edificio)
                 .filter(estado='pendiente')
                 .select_related('creador', 'edificio')[:20])
            t1 = time.perf_counter()
            latencias_listado.append((t1 - t0) * 1000.0)

        # ── 2. BENCHMARK PANEL DE INDICADORES (AGREGACIONES) ───────
        latencias_dashboard = []
        for _ in range(iteraciones):
            t0 = time.perf_counter()
            list(Incidencia.objects.del_edificio(edificio).values('estado').annotate(total=Count('id')))
            list(Incidencia.objects.del_edificio(edificio).values('prioridad').annotate(total=Count('id')))
            t1 = time.perf_counter()
            latencias_dashboard.append((t1 - t0) * 1000.0)

        # ── 3. BENCHMARK BÚSQUEDA POR TÍTULO ──────────────────────
        latencias_busqueda = []
        for _ in range(iteraciones):
            t0 = time.perf_counter()
            list(Incidencia.objects.del_edificio(edificio)
                 .filter(titulo__icontains='agua')[:20])
            t1 = time.perf_counter()
            latencias_busqueda.append((t1 - t0) * 1000.0)

        def calcular_metricas(lista):
            lista_ordenada = sorted(lista)
            n = len(lista_ordenada)
            p50 = lista_ordenada[int(n * 0.50)]
            p95 = lista_ordenada[int(n * 0.95)]
            p99 = lista_ordenada[int(n * 0.99)]
            promedio = sum(lista_ordenada) / n
            return promedio, p50, p95, p99

        def imprimir_fila(nombre, l):
            avg, p50, p95, p99 = calcular_metricas(l)
            estado = "✅ CUMPLE (<300ms)" if p95 < 300.0 else "❌ EXCEDE"
            self.stdout.write(f"{nombre:<25} | Prom: {avg:6.2f} ms | p50: {p50:6.2f} ms | p95: {p95:6.2f} ms | {estado}")

        self.stdout.write(self.style.HTTP_INFO("Resultados de Latencia:"))
        self.stdout.write("-" * 80)
        imprimir_fila("1. Listado paginado (20)", latencias_listado)
        imprimir_fila("2. Panel métricas (Group)", latencias_dashboard)
        imprimir_fila("3. Búsqueda por texto", latencias_busqueda)
        self.stdout.write("-" * 80)

        # ── 4. PLAN DE EJECUCIÓN (EXPLAIN) ─────────────────────────
        self.stdout.write(self.style.HTTP_INFO("\nPlan de Ejecución EXPLAIN (Demostración de uso de índices):"))
        self.stdout.write("-" * 80)

        sql_listado = """
        EXPLAIN SELECT id, titulo, estado, prioridad
        FROM incidencias_incidencia
        WHERE edificio_id = %s AND estado = 'pendiente'
        ORDER BY fecha_creacion DESC
        LIMIT 20;
        """

        with connection.cursor() as cursor:
            cursor.execute(sql_listado, [edificio.id])
            columnas = [col[0] for col in cursor.description]
            filas = cursor.fetchall()
            self.stdout.write(" | ".join(columnas))
            self.stdout.write("-" * 80)
            for f in filas:
                self.stdout.write(" | ".join(str(val) for val in f))

        self.stdout.write(self.style.SUCCESS("\n✅ Benchmark finalizado correctamente.\n"))
