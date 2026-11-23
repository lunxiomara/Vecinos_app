from django.contrib import admin
from .models import Edificio, Unidad, Perfil, Incidencia, Comentario, EventoIncidencia, OutboxMessage


# ─────────────────────────────────────────────
# EDIFICIO
# ─────────────────────────────────────────────
@admin.register(Edificio)
class EdificioAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'direccion')
    search_fields = ('nombre', 'direccion')


# ─────────────────────────────────────────────
# UNIDAD
# ─────────────────────────────────────────────
@admin.register(Unidad)
class UnidadAdmin(admin.ModelAdmin):
    list_display  = ('edificio', 'piso', 'numero')
    list_filter   = ('edificio',)
    search_fields = ('numero', 'edificio__nombre')


# ─────────────────────────────────────────────
# PERFIL
# ─────────────────────────────────────────────
@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display  = ('user', 'edificio', 'rol', 'unidad')
    list_filter   = ('edificio', 'rol')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'unidad')


# ─────────────────────────────────────────────
# EVENTO (solo lectura — historial inmutable)
# ─────────────────────────────────────────────
class EventoIncidenciaInline(admin.TabularInline):
    model         = EventoIncidencia
    extra         = 0
    readonly_fields = ('tipo', 'actor', 'estado_antes', 'estado_despues', 'detalle', 'fecha')
    can_delete    = False

    def has_add_permission(self, request, obj=None):
        return False


# ─────────────────────────────────────────────
# INCIDENCIA
# ─────────────────────────────────────────────
@admin.register(Incidencia)
class IncidenciaAdmin(admin.ModelAdmin):
    list_display   = ('id_incid', 'titulo', 'edificio', 'creador', 'estado', 'prioridad', 'fecha_creacion')
    list_filter    = ('edificio', 'estado', 'prioridad', 'categoria')
    search_fields  = ('titulo', 'descripcion', 'creador__username')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    inlines        = [EventoIncidenciaInline]

    def save_model(self, request, obj, form, change):
        obj._actor_username = request.user.username
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        """
        Los superusuarios ven todo.
        Los administradores de edificio solo ven su edificio.
        """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            edificio = request.user.perfil.edificio
            return qs.filter(edificio=edificio)
        except Exception:
            return qs.none()


# ─────────────────────────────────────────────
# COMENTARIO
# ─────────────────────────────────────────────
@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display  = ('autor', 'incidencia', 'es_interno', 'fecha_creacion')
    list_filter   = ('es_interno', 'incidencia__edificio')
    search_fields = ('autor__username', 'mensaje')


# ─────────────────────────────────────────────
# EVENTO (vista directa)
# ─────────────────────────────────────────────
@admin.register(EventoIncidencia)
class EventoIncidenciaAdmin(admin.ModelAdmin):
    list_display  = ('fecha', 'incidencia', 'tipo', 'actor', 'estado_antes', 'estado_despues')
    list_filter   = ('tipo',)
    search_fields = ('incidencia__titulo', 'actor__username')
    readonly_fields = ('fecha', 'tipo', 'actor', 'incidencia', 'estado_antes', 'estado_despues', 'detalle')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OutboxMessage)
class OutboxMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo_evento', 'estado', 'intentos', 'proximo_reintento', 'creado_en')
    list_filter = ('estado', 'tipo_evento')
    search_fields = ('tipo_evento', 'ultimo_error', 'dedupe_key')
    readonly_fields = (
        'tipo_evento', 'payload', 'estado', 'intentos', 'max_intentos',
        'ultimo_error', 'proximo_reintento', 'lease_token', 'dedupe_key',
        'creado_en', 'procesado_en',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
