from django.db import models
from django.db import router, transaction
from django.contrib.auth.models import User
from django.utils import timezone


# ─────────────────────────────────────────────
# EDIFICIO (entidad raíz del multi-tenancy)
# ─────────────────────────────────────────────
class Edificio(models.Model):
    id_edif   = models.AutoField(primary_key=True)
    nombre    = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)

    class Meta:
        verbose_name        = "Edificio"
        verbose_name_plural = "Edificios"

    def __str__(self):
        return self.nombre


# ─────────────────────────────────────────────
# UNIDAD (apartamento / unidad residencial)
# ─────────────────────────────────────────────
class Unidad(models.Model):
    id_unit  = models.AutoField(primary_key=True)
    edificio = models.ForeignKey(Edificio, on_delete=models.CASCADE, related_name='unidades')
    numero   = models.CharField(max_length=20, help_text="Ej: 101, PH-2, Local-3")
    piso     = models.CharField(max_length=10)

    class Meta:
        verbose_name        = "Unidad"
        verbose_name_plural = "Unidades"
        unique_together     = [('edificio', 'numero')]
        ordering            = ['piso', 'numero']

    def __str__(self):
        return f"{self.edificio.nombre} — Piso {self.piso} Unidad {self.numero}"


# ─────────────────────────────────────────────
# PERFIL (extiende User con rol y ubicación)
# ─────────────────────────────────────────────
class Perfil(models.Model):
    id_prfl  = models.AutoField(primary_key=True)
    ROL_CHOICES = [
        ('residente',     'Residente'),
        ('administrador', 'Administrador de edificio'),
        ('tecnico',       'Técnico'),
        ('auditor',       'Auditor'),
    ]

    user     = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    edificio = models.ForeignKey(Edificio, on_delete=models.CASCADE, related_name='residentes')
    unidad   = models.ForeignKey(
        Unidad, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='residentes',
        help_text="Apartamento/unidad del usuario (opcional para técnicos y auditores)"
    )
    rol      = models.CharField(max_length=20, choices=ROL_CHOICES, default='residente')
    # Campos heredados del MVP (se conservan para compatibilidad)
    piso     = models.CharField(max_length=10, blank=True, default='')
    puerta   = models.CharField(max_length=10, blank=True, default='')

    class Meta:
        verbose_name        = "Perfil"
        verbose_name_plural = "Perfiles"

    def __str__(self):
        return (
            f"{self.user.get_full_name() or self.user.username} "
            f"({self.edificio.nombre} — {self.get_rol_display()})"
        )

    # ── Helpers de rol ──────────────────────────────
    @property
    def es_residente(self):
        return self.rol == 'residente'

    @property
    def es_administrador(self):
        return self.rol == 'administrador'

    @property
    def es_tecnico(self):
        return self.rol == 'tecnico'

    @property
    def es_auditor(self):
        return self.rol == 'auditor'

    @property
    def puede_gestionar(self):
        """True si el usuario puede cambiar estados o asignar técnicos."""
        return self.rol in ('administrador', 'tecnico')


# ─────────────────────────────────────────────
# MANAGER con alcance por edificio
# ─────────────────────────────────────────────
class IncidenciaPorEdificioManager(models.Manager):
    """
    Manager personalizado que añade el método del_edificio().
    Garantiza que aunque una vista olvide filtrar,
    los datos nunca se mezclan entre edificios.
    """
    def del_edificio(self, edificio):
        return self.get_queryset().filter(edificio=edificio)

    def abiertas_del_edificio(self, edificio):
        return self.del_edificio(edificio).exclude(estado__in=['resuelta', 'cerrada'])


# ─────────────────────────────────────────────
# INCIDENCIA
# ─────────────────────────────────────────────
class Incidencia(models.Model):
    id_incid  = models.AutoField(primary_key=True)
    CATEGORIAS = [
        ('agua',          'Agua'),
        ('electricidad',  'Electricidad'),
        ('limpieza',      'Limpieza'),
        ('seguridad',     'Seguridad'),
        ('otros',         'Otros'),
    ]

    PRIORIDADES = [
        ('baja',  'Baja'),
        ('media', 'Media'),
        ('alta',  'Alta'),
    ]

    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('proceso',   'En Proceso'),
        ('resuelta',  'Resuelta'),
        ('cerrada',   'Cerrada'),
    ]

    # ── Claves foráneas ──────────────────────────────
    edificio         = models.ForeignKey(
        Edificio, on_delete=models.CASCADE,
        related_name='incidencias_edificio',
        null=True, blank=True           # null temporal para la migración de datos
    )
    creador          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incidencias')
    tecnico_asignado = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Técnico o empresa responsable asignada"
    )

    # ── Datos de la incidencia ───────────────────────
    titulo           = models.CharField(max_length=150)
    descripcion      = models.TextField()
    categoria        = models.CharField(max_length=20, choices=CATEGORIAS, default='otros')
    prioridad        = models.CharField(max_length=10, choices=PRIORIDADES, default='media')
    estado           = models.CharField(max_length=15, choices=ESTADOS,    default='pendiente')
    foto             = models.ImageField(upload_to='incidencias/', blank=True, null=True)
    nota_interna     = models.TextField(
        blank=True, null=True,
        help_text="Notas visibles únicamente para administradores y técnicos"
    )

    # ── Concurrencia y Versión (Bloqueo Optimista) ────
    version          = models.PositiveIntegerField(
        default=1,
        verbose_name="Versión de concurrencia",
        help_text="Incrementado automáticamente para control de concurrencia optimista"
    )

    # ── Fechas ───────────────────────────────────────
    fecha_creacion      = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    # ── Managers ─────────────────────────────────────
    objects       = IncidenciaPorEdificioManager()   # manager personalizado (default)

    def save(self, *args, **kwargs):
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            return super().save(*args, **kwargs)

    class Meta:
        verbose_name        = "Incidencia"
        verbose_name_plural = "Incidencias"
        ordering            = ['-fecha_creacion']
        indexes = [
            # indice compuesto principal: acelera listados y filtros por edificio y estado
            models.Index(fields=['edificio', 'estado', '-fecha_creacion'], name='idx_inc_edif_est_fecha'),
            # Índice compuesto para el panel de indicadores (M3 & M6)
            models.Index(fields=['edificio', 'prioridad'], name='idx_inc_edif_prio'),
            models.Index(fields=['edificio', 'categoria'], name='idx_inc_edif_cat'),
            models.Index(fields=['prioridad'], name='idx_inc_prio'),
            models.Index(fields=['estado'], name='idx_inc_estado'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(estado__in=['pendiente', 'proceso', 'resuelta', 'cerrada']),
                name='chk_inc_estado_valido'
            ),
            models.CheckConstraint(
                check=models.Q(prioridad__in=['baja', 'media', 'alta']),
                name='chk_inc_prioridad_valida'
            ),
        ]

    def __str__(self):
        return f"#{self.id_incid} - {self.titulo} ({self.get_estado_display()})"

    @property
    def puede_editar_residente(self):
        return self.estado == 'pendiente'

    # ── Maquina de estados ───────────────────────────
    TRANSICIONES_VALIDAS = {
        'pendiente': ['proceso'],
        'proceso':   ['resuelta', 'pendiente'],
        'resuelta':  ['cerrada', 'proceso'],    # puede reabrirse
        'cerrada':   [],                         # estado terminal
    }

    def puede_transicionar_a(self, nuevo_estado):
        return nuevo_estado in self.TRANSICIONES_VALIDAS.get(self.estado, [])


# ─────────────────────────────────────────────
# EVENTO DE INCIDENCIA (historial inmutable)
# ─────────────────────────────────────────────
class EventoIncidencia(models.Model):
    id_evinc = models.AutoField(primary_key=True)
    TIPOS_EVENTO = [
        ('creacion',          'Creación'),
        ('cambio_estado',     'Cambio de estado'),
        ('asignacion',        'Asignación de técnico'),
        ('reapertura',        'Reapertura'),
        ('comentario',        'Comentario añadido'),
    ]

    incidencia   = models.ForeignKey(Incidencia, on_delete=models.CASCADE, related_name='eventos')
    tipo         = models.CharField(max_length=30, choices=TIPOS_EVENTO)
    actor        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='eventos')
    estado_antes = models.CharField(max_length=15, blank=True, null=True)
    estado_despues = models.CharField(max_length=15, blank=True, null=True)
    detalle      = models.TextField(blank=True, default='')
    fecha        = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Evento de incidencia"
        verbose_name_plural = "Eventos de incidencia"
        ordering            = ['fecha']
        # Tabla de solo-lectura: no se borra, no se edita
        default_permissions = ('view',)
        indexes = [
            models.Index(fields=['incidencia', 'fecha'], name='idx_evento_inc_fecha'),
        ]

    def __str__(self):
        return f"[{self.fecha:%Y-%m-%d %H:%M}] {self.get_tipo_display()} — #{self.incidencia_id}"


# ─────────────────────────────────────────────
# COMENTARIO
# ─────────────────────────────────────────────
class ComentarioPorEdificioManager(models.Manager):
    def del_edificio(self, edificio):
        return self.get_queryset().filter(incidencia__edificio=edificio)


class Comentario(models.Model):
    incidencia    = models.ForeignKey(Incidencia, on_delete=models.CASCADE, related_name='comentarios')
    autor         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comentarios')
    mensaje       = models.TextField()
    es_interno    = models.BooleanField(
        default=False,
        help_text="Si es True, solo lo ven administradores y técnicos"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    objects = ComentarioPorEdificioManager()

    class Meta:
        verbose_name        = "Comentario"
        verbose_name_plural = "Comentarios"
        ordering            = ['fecha_creacion']
        indexes = [
            models.Index(fields=['incidencia', 'fecha_creacion'], name='idx_coment_inc_fecha'),
        ]

    def __str__(self):
        return f"Comentario de {self.autor.username} en #{self.incidencia_id}"


# ─────────────────────────────────────────────
# REGISTRO DE IDEMPOTENCIA (M4)
# ─────────────────────────────────────────────
class IdempotencyRecord(models.Model):
    """
    Almacena respuestas de peticiones POST con cabecera Idempotency-Key.
    Garantiza que reintentos de clientes externos no dupliquen incidencias.
    """
    key           = models.CharField(max_length=128, db_index=True)
    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='idempotency_keys')
    method        = models.CharField(max_length=10)
    path          = models.CharField(max_length=255)
    status_code   = models.IntegerField()
    response_body = models.JSONField(default=dict)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Registro de Idempotencia"
        verbose_name_plural = "Registros de Idempotencia"
        unique_together     = [('key', 'user', 'path')]
        indexes = [
            models.Index(fields=['key', 'user']),
        ]

    def __str__(self):
        return f"{self.key} | {self.user.username} -> {self.status_code}"


class OutboxMessage(models.Model):
    ESTADOS = [
        ('PENDING', 'Pendiente'),
        ('PROCESSING', 'Procesando'),
        ('PROCESSED', 'Procesado'),
        ('FAILED', 'Fallido (Dead Letter Queue)'),
    ]

    tipo_evento = models.CharField(
        max_length=60,
        help_text='Ej: INCIDENCIA_CREADA, CAMBIO_ESTADO, ALERTA_SLA',
    )
    payload = models.JSONField(help_text='Datos completos del evento para despacho desacoplado')
    estado = models.CharField(max_length=15, choices=ESTADOS, default='PENDING', db_index=True)
    intentos = models.PositiveIntegerField(default=0)
    max_intentos = models.PositiveIntegerField(default=3)
    ultimo_error = models.TextField(blank=True, default='')
    proximo_reintento = models.DateTimeField(default=timezone.now, db_index=True)
    lease_token = models.CharField(max_length=36, blank=True, default='')
    dedupe_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    procesado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Mensaje Outbox"
        verbose_name_plural = "Mensajes Outbox"
        ordering = ['creado_en']
        indexes = [
            models.Index(fields=['estado', 'proximo_reintento'], name='idx_outbox_est_reintento'),
        ]

    def __str__(self):
        return f"{self.tipo_evento} [{self.estado}] #{self.pk}"
