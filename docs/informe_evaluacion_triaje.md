# Informe de Evaluación del Triaje — VecinosApp

## 1. Propósito y alcance
El objetivo de este informe es documentar la implementación y evaluación inicial del módulo de triaje (`incidencias/triage.py`) en el proyecto **VecinosApp**, encargado de clasificar automáticamente las incidencias reportadas por residentes en **categoría** (`agua`, `electricidad`, `seguridad`, `limpieza`, `otros`) y **prioridad** (`alta`, `media`, `baja`), junto con un nivel de confianza y justificación del resultado.

## 2. Despliegue del entorno desde cero
El entorno de ejecución se estandarizó mediante el script `levantar_entorno.ps1` en la raíz del proyecto, permitiendo inicializar el entorno virtual, verificar dependencias, aplicar migraciones y arrancar el servidor Django en un solo paso (`.\levantar_entorno.ps1`).

## 3. Enfoque de triaje implementado
Se implementó la función `evaluar_incidencia(titulo, descripcion)` en `incidencias/triage.py` mediante normalización de texto y reglas léxicas ponderadas:
- **Categorización:** evalúa coincidencias de términos clave por dominio (`agua`, `electricidad`, `seguridad`, `limpieza`) y asigna `otros` con confianza base (`0.45`) cuando no hay coincidencias. La confianza escala según el número de coincidencias hasta un máximo de `0.95`.
- **Priorización:** detecta indicadores críticos o de riesgo (`alta`), fallos operativos o deterioro moderado (`media`) o asigna prioridad estándar (`baja`) cuando no se identifican términos de urgencia.

## 4. Casos de prueba y resultados

| # | Título de la incidencia | Descripción | Categoría | Prioridad | Confianza | Observación |
|---|---|---|---|---|---|---|
| 1 | Fuga de agua en tubería principal | Filtración constante en zona común | `agua` | `alta` | `0.95` | Clasificación correcta; detecta riesgo por fuga. |
| 2 | Luminaria dañada en pasillo | Bombillo fundido en el acceso del piso | `electricidad` | `media` | `0.90` | Clasificación correcta; deterioro moderado. |
| 3 | Portón principal con fallo | El motor del portón no abre con normalidad | `seguridad` | `media` | `0.75` | Clasificación correcta; fallo operativo en acceso. |
| 4 | Basura acumulada en cuarto de aseo | Residuos sin recoger desde ayer | `limpieza` | `baja` | `0.95` | Categoría correcta; prioridad baja por ausencia de términos críticos. |
| 5 | Solicitud de información sobre reglamento | Consulta general de convivencia | `otros` | `baja` | `0.45` | Respaldo correcto a `otros` y prioridad `baja`. |

## 5. Hallazgos, limitaciones y mejoras propuestas
- **Hallazgos:** el sistema responde de forma determinista, rápida y explicable en los 5 escenarios evaluados, entregando un motivo claro para cada decisión.
- **Limitaciones:** al basarse en palabras clave exactas/subcadenas, casos ambiguos, con errores ortográficos no contemplados o con jerga local pueden requerir ampliación del diccionario de términos o desempate cuando dos categorías empatan en puntaje.
- **Mejoras futuras:** ampliar el vocabulario de reglas con sinónimos locales, incorporar pruebas unitarias automatizadas (`tests.py`) para `evaluar_incidencia` y conectar el resultado del triaje al flujo de creación de incidencias si se desea autocompletar categoría y prioridad sugerida.