from collections import deque
from dataclasses import dataclass, asdict
import threading
import time
from django.utils import timezone

UMBRAL_LATENCIA_MS = 250.0
MAX_TRAZAS = 100
_LOCK = threading.Lock()
_TRAZAS = deque(maxlen=MAX_TRAZAS)
_METRICAS = {
    'total_peticiones': 0,
    'total_errores': 0,
    'total_lentas': 0,
    'suma_duracion_ms': 0.0,
    'max_duracion_ms': 0.0,
    'alertas_disparadas': 0,
    'ultima_alerta': None,
}


@dataclass
class TrazaPeticion:
    timestamp: str
    metodo: str
    ruta: str
    status: int
    duracion_ms: float
    usuario: str
    alerta_disparada: bool
    motivo_alerta: str


def registrar_traza(request, response, duracion_ms):
    duracion_redondeada = round(duracion_ms, 2)
    status = getattr(response, 'status_code', 200)
    usuario = (
        request.user.username
        if hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False)
        else 'anonimo'
    )

    motivos = []
    if duracion_redondeada >= UMBRAL_LATENCIA_MS:
        motivos.append(f'Latencia >= {UMBRAL_LATENCIA_MS} ms ({duracion_redondeada} ms)')
    if status >= 400:
        motivos.append(f'Estado HTTP {status}')

    alerta_disparada = len(motivos) > 0
    motivo_texto = ' | '.join(motivos) if motivos else '-'
    ahora_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S')

    traza = TrazaPeticion(
        timestamp=ahora_str,
        metodo=request.method,
        ruta=request.path,
        status=status,
        duracion_ms=duracion_redondeada,
        usuario=usuario,
        alerta_disparada=alerta_disparada,
        motivo_alerta=motivo_texto,
    )

    with _LOCK:
        _TRAZAS.appendleft(traza)
        _METRICAS['total_peticiones'] += 1
        _METRICAS['suma_duracion_ms'] += duracion_redondeada
        if duracion_redondeada > _METRICAS['max_duracion_ms']:
            _METRICAS['max_duracion_ms'] = duracion_redondeada
        if status >= 400:
            _METRICAS['total_errores'] += 1
        if duracion_redondeada >= UMBRAL_LATENCIA_MS:
            _METRICAS['total_lentas'] += 1
        if alerta_disparada:
            _METRICAS['alertas_disparadas'] += 1
            _METRICAS['ultima_alerta'] = {
                'timestamp': ahora_str,
                'ruta': request.path,
                'motivo': motivo_texto,
            }


def obtener_estado_observabilidad():
    with _LOCK:
        total = _METRICAS['total_peticiones']
        promedio_ms = round(_METRICAS['suma_duracion_ms'] / total, 2) if total > 0 else 0.0
        alerta_activa = (
            _METRICAS['total_errores'] > 0
            or _METRICAS['total_lentas'] > 0
            or promedio_ms >= UMBRAL_LATENCIA_MS
        )
        return {
            'umbral_latencia_ms': UMBRAL_LATENCIA_MS,
            'alerta_activa': alerta_activa,
            'ultima_alerta': _METRICAS['ultima_alerta'],
            'metricas': {
                'total_peticiones': total,
                'promedio_duracion_ms': promedio_ms,
                'max_duracion_ms': round(_METRICAS['max_duracion_ms'], 2),
                'total_errores': _METRICAS['total_errores'],
                'total_lentas': _METRICAS['total_lentas'],
                'alertas_disparadas': _METRICAS['alertas_disparadas'],
            },
            'trazas': [asdict(t) for t in _TRAZAS],
        }


def reiniciar_observabilidad():
    with _LOCK:
        _TRAZAS.clear()
        _METRICAS['total_peticiones'] = 0
        _METRICAS['total_errores'] = 0
        _METRICAS['total_lentas'] = 0
        _METRICAS['suma_duracion_ms'] = 0.0
        _METRICAS['max_duracion_ms'] = 0.0
        _METRICAS['alertas_disparadas'] = 0
        _METRICAS['ultima_alerta'] = None


class ObservabilidadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inicio = time.perf_counter()
        response = self.get_response(request)
        duracion_ms = (time.perf_counter() - inicio) * 1000.0
        if not request.path.startswith(('/observabilidad/', '/incidencias/observabilidad/')):
            registrar_traza(request, response, duracion_ms)
        return response