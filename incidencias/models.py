from django.db import models
from django.contrib.auth.models import User

class Edificio(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200)

    class Meta:
        verbose_name = "Edificio"
        verbose_name_plural = "Edificios"

    def __str__(self):
        return self.nombre

class Perfil(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    edificio = models.ForeignKey(Edificio, on_delete=models.CASCADE, related_name='residentes')
    piso = models.CharField(max_length=10)
    puerta = models.CharField(max_length=10)

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfiles"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.edificio.nombre} - Piso {self.piso} {self.puerta})"

class Incidencia(models.Model):
    CATEGORIAS = [
        ('agua', 'Agua'),
        ('electricidad', 'Electricidad'),
        ('limpieza', 'Limpieza'),
        ('seguridad', 'Seguridad'),
        ('otros', 'Otros'),
    ]

    PRIORIDADES = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
    ]

    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('proceso', 'En Proceso'),
        ('resuelta', 'Resuelta'),
        ('cerrada', 'Cerrada'),
    ]

    titulo = models.CharField(max_length=150)
    descripcion = models.TextField()
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='otros')
    prioridad = models.CharField(max_length=10, choices=PRIORIDADES, default='media')
    estado = models.CharField(max_length=15, choices=ESTADOS, default='pendiente')
    foto = models.ImageField(upload_to='incidencias/', blank=True, null=True)
    creador = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incidencias')
    tecnico_asignado = models.CharField(max_length=100, blank=True, null=True, help_text="Técnico o empresa responsable asignada")
    nota_interna = models.TextField(blank=True, null=True, help_text="Notas visibles únicamente para administradores")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Incidencia"
        verbose_name_plural = "Incidencias"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"#{self.id} - {self.titulo} ({self.get_estado_display()})"

    @property
    def puede_editar_residente(self):
        return self.estado == 'pendiente'

class Comentario(models.Model):
    incidencia = models.ForeignKey(Incidencia, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comentarios')
    mensaje = models.TextField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comentario"
        verbose_name_plural = "Comentarios"
        ordering = ['fecha_creacion']

    def __str__(self):
        return f"Comentario de {self.autor.username} en #{self.incidencia_id}"