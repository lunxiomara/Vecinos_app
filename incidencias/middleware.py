"""
Middleware que fija el edificio activo del usuario autenticado
en cada request. Las vistas lo usan via request.edificio_activo
sin repetir la lógica de obtención.
"""


class EdificioActivoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.edificio_activo = None   # valor por defecto (anónimo)

        if request.user.is_authenticated:
            try:
                request.edificio_activo = request.user.perfil.edificio
            except Exception:
                # Usuario sin perfil (ej: superusuario sin perfil asignado)
                request.edificio_activo = None

        response = self.get_response(request)
        return response
