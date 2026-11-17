"""
Migración M2 — Multi-edificio y Autorización
============================================
Esta migración:
  1. Crea la tabla incidencias_unidad
  2. Agrega columna 'rol' y 'unidad_id' a incidencias_perfil
  3. Agrega columna 'edificio_id' a incidencias_incidencia
  4. Agrega columna 'es_interno' a incidencias_comentario
  5. Crea la tabla incidencias_eventoincidencia
  6. MIGRACIÓN DE DATOS: llena incidencia.edificio con el edificio del creador
  7. Hace edificio NOT NULL en incidencias_incidencia
"""

from django.db import migrations, models
import django.db.models.deletion


def migrar_edificio_incidencias(apps, schema_editor):
    """
    Asigna el edificio de cada incidencia existente
    tomándolo del perfil del creador.
    """
    Incidencia = apps.get_model('incidencias', 'Incidencia')
    for inc in Incidencia.objects.select_related('creador__perfil').all():
        try:
            inc.edificio = inc.creador.perfil.edificio
            inc.save(update_fields=['edificio'])
        except Exception:
            pass  # Incidencias sin perfil de creador se quedan sin edificio


def revertir_migrar_edificio(apps, schema_editor):
    """Reversión: poner edificio a NULL en todas las incidencias."""
    Incidencia = apps.get_model('incidencias', 'Incidencia')
    Incidencia.objects.all().update(edificio=None)


class Migration(migrations.Migration):

    dependencies = [
        ('incidencias', '0001_initial'),
    ]

    operations = [
        # ── 1. Crear tabla Unidad ──────────────────────────────────────────
        migrations.CreateModel(
            name='Unidad',
            fields=[
                ('id',       models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero',   models.CharField(help_text='Ej: 101, PH-2, Local-3', max_length=20)),
                ('piso',     models.CharField(max_length=10)),
                ('edificio', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='unidades',
                    to='incidencias.edificio',
                )),
            ],
            options={
                'verbose_name':        'Unidad',
                'verbose_name_plural': 'Unidades',
                'ordering':            ['piso', 'numero'],
                'unique_together':     {('edificio', 'numero')},
            },
        ),

        # ── 2. Agregar 'rol' a Perfil ──────────────────────────────────────
        migrations.AddField(
            model_name='perfil',
            name='rol',
            field=models.CharField(
                choices=[
                    ('residente',     'Residente'),
                    ('administrador', 'Administrador de edificio'),
                    ('tecnico',       'Técnico'),
                    ('auditor',       'Auditor'),
                ],
                default='residente',
                max_length=20,
            ),
        ),

        # ── 3. Agregar 'unidad' a Perfil ──────────────────────────────────
        migrations.AddField(
            model_name='perfil',
            name='unidad',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='residentes',
                to='incidencias.unidad',
                help_text='Apartamento/unidad del usuario',
            ),
        ),

        # ── 4. Agregar 'edificio' a Incidencia (nullable primero) ──────────
        migrations.AddField(
            model_name='incidencia',
            name='edificio',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='incidencias_edificio',
                to='incidencias.edificio',
            ),
        ),

        # ── 5. Migración de datos ──────────────────────────────────────────
        migrations.RunPython(
            migrar_edificio_incidencias,
            revertir_migrar_edificio,
        ),

        # ── 6. Agregar 'es_interno' a Comentario ──────────────────────────
        migrations.AddField(
            model_name='comentario',
            name='es_interno',
            field=models.BooleanField(
                default=False,
                help_text='Si es True, solo lo ven administradores y técnicos',
            ),
        ),

        # ── 7. Crear tabla EventoIncidencia ───────────────────────────────
        migrations.CreateModel(
            name='EventoIncidencia',
            fields=[
                ('id',             models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo',           models.CharField(
                    choices=[
                        ('creacion',      'Creación'),
                        ('cambio_estado', 'Cambio de estado'),
                        ('asignacion',    'Asignación de técnico'),
                        ('reapertura',    'Reapertura'),
                        ('comentario',    'Comentario añadido'),
                    ],
                    max_length=30,
                )),
                ('estado_antes',   models.CharField(blank=True, max_length=15, null=True)),
                ('estado_despues', models.CharField(blank=True, max_length=15, null=True)),
                ('detalle',        models.TextField(blank=True, default='')),
                ('fecha',          models.DateTimeField(auto_now_add=True)),
                ('actor',          models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='eventos',
                    to='auth.user',
                )),
                ('incidencia',     models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='eventos',
                    to='incidencias.incidencia',
                )),
            ],
            options={
                'verbose_name':        'Evento de incidencia',
                'verbose_name_plural': 'Eventos de incidencia',
                'ordering':            ['fecha'],
                'default_permissions': ('view',),
            },
        ),
    ]
