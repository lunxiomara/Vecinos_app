from django.contrib import admin
from .models import Edificio, Perfil, Incidencia, Comentario

@admin.register(Edificio)
class EdificioAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'direccion')
    search_fields = ('nombre', 'direccion')

@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('user', 'edificio', 'piso', 'puerta')
    list_filter = ('edificio',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'piso', 'puerta')

class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 1
    readonly_fields = ('fecha_creacion',)

@admin.register(Incidencia)
class IncidenciaAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'creador', 'categoria', 'prioridad', 'estado', 'tecnico_asignado', 'fecha_creacion')
    list_filter = ('estado', 'categoria', 'prioridad', 'fecha_creacion')
    search_fields = ('titulo', 'descripcion', 'creador__username', 'tecnico_asignado')
    list_editable = ('estado', 'prioridad')
    inlines = [ComentarioInline]
    date_hierarchy = 'fecha_creacion'
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    fieldsets = (
        ('Información Principal', {
            'fields': ('titulo', 'descripcion', 'creador', 'foto')
        }),
        ('Clasificación y Estado', {
            'fields': ('categoria', 'prioridad', 'estado')
        }),
        ('Gestión Administrativa', {
            'fields': ('tecnico_asignado', 'nota_interna')
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',),
        }),
    )

@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ('id', 'incidencia', 'autor', 'fecha_creacion')
    list_filter = ('fecha_creacion',)
    search_fields = ('mensaje', 'autor__username', 'incidencia__titulo')
