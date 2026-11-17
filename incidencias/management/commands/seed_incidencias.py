"""
Comando de Django para Carga Masiva de Rendimiento (M3)
======================================================
Genera hasta 100.000 incidencias usando bulk_create en lotes.
Permite evaluar la latencia p95 y los índices compuestos.

Uso:
    python manage.py seed_incidencias --cantidad 100000
    python manage.py seed_incidencias --cantidad 5000 --clean
"""

import random
import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.models import User
from incidencias.models import Edificio, Perfil, Incidencia


TITULOS_MUESTRA = [
    "Fuga de agua en tubería principal del piso",
    "Fallo en iluminación de pasillo común",
    "Ruido excesivo en horario de descanso",
    "Cerradura de portón principal averiada",
    "Humedad en techo de pasillo",
    "Ascensor principal fuera de servicio",
    "Intercomunicador no timbra en la unidad",
    "Basura acumulada en zona de reciclaje",
    "Puerta de emergencia no cierra correctamente",
    "Filtración de agua en zona de parqueaderos",
    "Cámara de seguridad del hall desconectada",
    "Alarma de incendios emitiendo pitido intermitente"
]

DESCRIPCIONES = [
    "Se evidencia la situación desde horas de la mañana, solicitamos intervención técnica.",
    "El problema persiste y genera incomodidad a los residentes del sector.",
    "Reportado con anterioridad verbalmente, se formaliza el caso para seguimiento.",
    "Situación recurrente que requiere inspección y cambio de repuesto."
]

CATEGORIAS = ['agua', 'electricidad', 'limpieza', 'seguridad', 'otros']
PRIORIDADES = ['baja', 'media', 'alta']
ESTADOS = ['pendiente', 'proceso', 'resuelta', 'cerrada']


class Command(BaseCommand):
    help = "Pobla la base de datos con incidencias sintéticas de alto rendimiento (bulk_create)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--cantidad',
            type=int,
            default=10000,
            help='Número total de incidencias a crear (ej: 100000)'
        )
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Elimina las incidencias existentes antes de poblar'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Tamaño de lote para bulk_create (default: 1000)'
        )

    def handle(self, *args, **options):
        cantidad = options['cantidad']
        clean = options['clean']
        batch_size = options['batch_size']

        self.stdout.write(self.style.NOTICE(f"=== Iniciando generación masiva de {cantidad:,} incidencias ==="))
        t_inicio = time.time()

        # Edificio y usuario de referencia para el benchmark
        edificio, _ = Edificio.objects.get_or_create(
            nombre="Torre Mayor Benchmark",
            defaults={'direccion': 'Av. Principal # 100-50'}
        )
        
        user_bench, _ = User.objects.get_or_create(
            username="usuario_benchmark",
            defaults={'first_name': 'Tester', 'last_name': 'Performance', 'email': 'bench@vecinos.local'}
        )
        if not hasattr(user_bench, 'perfil'):
            Perfil.objects.create(user=user_bench, edificio=edificio, rol='residente')

        if clean:
            self.stdout.write("Limpiando incidencias del edificio benchmark...")
            Incidencia.objects.filter(edificio=edificio).delete()

        ahora = timezone.now()
        total_creados = 0

        # Creación en lotes optimizados
        for offset in range(0, cantidad, batch_size):
            lote_tamano = min(batch_size, cantidad - offset)
            objetos_lote = []

            for i in range(lote_tamano):
                dias_atras = random.randint(0, 365)
                fecha_sintetica = ahora - timedelta(days=dias_atras, minutes=random.randint(0, 1440))
                
                estado = random.choice(ESTADOS)
                tecnico = f"Técnico Especialista #{random.randint(1, 10)}" if estado in ('proceso', 'resuelta') else None

                inc = Incidencia(
                    edificio=edificio,
                    creador=user_bench,
                    titulo=f"{random.choice(TITULOS_MUESTRA)} [{offset + i + 1}]",
                    descripcion=random.choice(DESCRIPCIONES),
                    categoria=random.choice(CATEGORIAS),
                    prioridad=random.choice(PRIORIDADES),
                    estado=estado,
                    tecnico_asignado=tecnico,
                    version=1,
                    fecha_creacion=fecha_sintetica,
                    fecha_actualizacion=fecha_sintetica
                )
                objetos_lote.append(inc)

            with transaction.atomic():
                Incidencia.objects.bulk_create(objetos_lote, batch_size=batch_size)

            total_creados += lote_tamano
            porcentaje = (total_creados / cantidad) * 100
            self.stdout.write(f"  -> Insertados {total_creados:,}/{cantidad:,} ({porcentaje:.1f}%)")

        t_total = time.time() - t_inicio
        tasa = total_creados / t_total if t_total > 0 else 0

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ ÉXITO: {total_creados:,} incidencias creadas en {t_total:.2f} s ({tasa:,.0f} registros/s)."
        ))
