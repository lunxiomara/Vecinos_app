# Informe de Rendimiento y Concurrencia — Módulo 3
**Proyecto:** Vecinos App — Plataforma de Gestión de Incidencias  
**Fecha de Evaluación:** 2026-11-16  
**Criterio de Aceptación:** Latencia p95 < 300 ms, Cero consultas N+1, y concurrencia serializada.

---

## 1. Resumen Ejecutivo de Resultados

Las optimizaciones implementadas en la base de datos (índices compuestos, restricciones Check y bloqueo a nivel de fila) arrojaron los siguientes resultados empíricos:

| Tipo de Operación | Promedio (ms) | Mediana p50 (ms) | **Percentil p95 (ms)** | Meta del Taller | Resultado |
|---|---|---|---|---|---|
| **1. Listado paginado (20 filas)** | 42.09 ms | 40.55 ms | **54.47 ms** | < 300 ms | **Cumple con holgura (6x más rápido)** |
| **2. Panel métricas (Group By)** | 9.32 ms | 9.39 ms | **12.56 ms** | < 300 ms | **Cumple con holgura (24x más rápido)** |
| **3. Búsqueda por texto (icontains)** | 16.08 ms | 16.40 ms | **19.18 ms** | < 300 ms | **Cumple con holgura (15x más rápido)** |

---

## 2. Erradicación de Consultas N+1

- **Problema previo:** Cada elemento renderizado disparaba consultas adicionales para obtener el edificio y el creador (generando $1 + N$ consultas SQL).
- **Solución implementada:** Uso estricto de `select_related('creador', 'creador__perfil', 'edificio')` en todos los métodos de consulta.
- **Validación automática:** Prueba unitaria `OptimizacionConsultasNPlusOneTest.test_listado_no_tiene_consultas_n_mas_uno` con `assertNumQueries(1)`:
  - Total de registros iterados: 20
  - Total de consultas ejecutadas a la base de datos: **1**

---

## 3. Demostración de Índices Compuestos (`EXPLAIN`)

Consulta evaluada:
```sql
EXPLAIN SELECT id, titulo, estado, prioridad
FROM incidencias_incidencia
WHERE edificio_id = 1 AND estado = 'pendiente'
ORDER BY fecha_creacion DESC
LIMIT 20;
```

### Salida del Plan de Ejecución:
```text
+----+-------------+------------------------+------+-----------------------------------------------------------------------+-------------------------+---------+-------------+------+-------------+
| id | select_type | table                  | type | possible_keys                                                         | key                     | key_len | ref         | rows | Extra       |
+----+-------------+------------------------+------+-----------------------------------------------------------------------+-------------------------+---------+-------------+------+-------------+
|  1 | SIMPLE      | incidencias_incidencia | ref  | idx_inc_edif_est_fecha,idx_inc_edif_prio,idx_inc_edif_cat,idx_inc_est  | idx_inc_edif_est_fecha  | 71      | const,const | 1279 | Using where |
+----+-------------+------------------------+------+-----------------------------------------------------------------------+-------------------------+---------+-------------+------+-------------+
```

> **Análisis del Plan:**
> - `type: ref`: No se realiza un escaneo de tabla completa (`ALL`); la base de datos utiliza acceso por referencia directa.
> - `key: idx_inc_edif_est_fecha`: El motor seleccionó el índice compuesto `(edificio, estado, -fecha_creacion)`.
> - `key_len: 71`: Se consumen las dos columnas de filtrado simultáneamente (`edificio_id` y `estado`).

---

## 4. Control de Concurrencia Bajo Estrés (20 Hilos Concurrentes)

- **Caso de uso:** 20 hilos simultáneos (`threading.Thread`) intentan asignar técnicos distintos a la misma incidencia en la misma fracción de segundo.
- **Mecanismo:** Bloqueo pesimista mediante `select_for_update()` en `incidencias/services.py` dentro de transacciones atómicas (`transaction.atomic()`).
- **Mecanismo optimista:** Campo `version = models.PositiveIntegerField(default=1)` que incrementa en cada mutación e impide sobrescrituras sucias (`dirty writes`).
- **Resultado de la prueba (`test_veinte_hilos_asignando_tecnico_concurrente`):**
  - Versión final esperada: 21 (1 inicial + 20 mutaciones secuencializadas)
  - Versión final obtenida: **21**
  - Eventos inmutables de auditoría registrados: **20**
  - Condición de carrera: **0 colisiones, 0 inconsistencias de datos**.
