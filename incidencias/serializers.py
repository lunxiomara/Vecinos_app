"""
Serializadores de Django REST Framework — API v1 (M4)
====================================================
Implementa serializadores anidados, validaciones de dominio y
optimización con select_related/prefetch_related.
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema_field
from .models import Edificio, Unidad, Perfil, Incidencia, Comentario, EventoIncidencia


class EdificioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edificio
        fields = ['id', 'nombre', 'direccion']


class CreadorSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'nombre_completo']

    @extend_schema_field(serializers.CharField)
    def get_nombre_completo(self, obj) -> str:
        return obj.get_full_name() or obj.username


class EventoIncidenciaSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True)

    class Meta:
        model = EventoIncidencia
        fields = ['id', 'tipo', 'actor_username', 'estado_antes', 'estado_despues', 'detalle', 'fecha']


class ComentarioSerializer(serializers.ModelSerializer):
    autor = CreadorSerializer(read_only=True)

    class Meta:
        model = Comentario
        fields = ['id', 'incidencia', 'autor', 'mensaje', 'es_interno', 'fecha_creacion']
        read_only_fields = ['autor', 'fecha_creacion']

    def create(self, validated_data):
        validated_data['autor'] = self.context['request'].user
        return super().create(validated_data)


class IncidenciaListSerializer(serializers.ModelSerializer):
    """Serializador optimizado para listados y filtros paginados."""
    creador = CreadorSerializer(read_only=True)
    edificio = EdificioSerializer(read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    prioridad_display = serializers.CharField(source='get_prioridad_display', read_only=True)

    class Meta:
        model = Incidencia
        fields = [
            'id', 'titulo', 'categoria', 'prioridad', 'prioridad_display',
            'estado', 'estado_display', 'tecnico_asignado', 'creador',
            'edificio', 'version', 'fecha_creacion', 'fecha_actualizacion'
        ]


class IncidenciaDetailSerializer(serializers.ModelSerializer):
    """Serializador detallado con eventos inmutables y comentarios asociados."""
    creador = CreadorSerializer(read_only=True)
    edificio = EdificioSerializer(read_only=True)
    comentarios = ComentarioSerializer(many=True, read_only=True)
    eventos = EventoIncidenciaSerializer(many=True, read_only=True)

    class Meta:
        model = Incidencia
        fields = [
            'id', 'titulo', 'descripcion', 'categoria', 'prioridad',
            'estado', 'tecnico_asignado', 'foto', 'nota_interna',
            'creador', 'edificio', 'version', 'fecha_creacion',
            'fecha_actualizacion', 'comentarios', 'eventos'
        ]


class IncidenciaCreateSerializer(serializers.ModelSerializer):
    """Serializador para reportar nuevas incidencias con validación segura."""
    class Meta:
        model = Incidencia
        fields = ['id', 'titulo', 'descripcion', 'categoria', 'prioridad', 'foto']

    def validate_titulo(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("El título debe tener al menos 10 caracteres.")
        return value.strip()

    def create(self, validated_data):
        user = self.context['request'].user
        edificio = getattr(self.context['request'], 'edificio_activo', None)
        if not edificio and hasattr(user, 'perfil'):
            edificio = user.perfil.edificio

        if not edificio:
            raise serializers.ValidationError("El usuario no tiene un edificio asociado en su perfil.")

        validated_data['creador'] = user
        validated_data['edificio'] = edificio
        validated_data['estado'] = 'pendiente'
        validated_data['version'] = 1

        incidencia = super().create(validated_data)

        # Evento inmutable de auditoría
        EventoIncidencia.objects.create(
            incidencia=incidencia,
            tipo='creacion',
            actor=user,
            estado_despues='pendiente',
            detalle=f"Incidencia creada vía API REST v1 por {user.username}"
        )
        return incidencia


class CambiarEstadoSerializer(serializers.Serializer):
    nuevo_estado = serializers.ChoiceField(choices=Incidencia.ESTADOS)
    detalle = serializers.CharField(required=False, allow_blank=True, default='')
    version_esperada = serializers.IntegerField(required=False, allow_null=True, default=None)


class AsignarTecnicoSerializer(serializers.Serializer):
    nombre_tecnico = serializers.CharField(max_length=100)
    version_esperada = serializers.IntegerField(required=False, allow_null=True, default=None)
