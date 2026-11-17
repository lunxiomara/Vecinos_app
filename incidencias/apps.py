from django.apps import AppConfig


class IncidenciasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'incidencias'
    verbose_name       = 'Gestión de Incidencias'

    def ready(self):
        # Cargar las reglas de permisos al arrancar Django
        import incidencias.rules  # noqa: F401
        # Cargar señales
        import incidencias.signals  # noqa: F401
