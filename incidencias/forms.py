from django import forms
from django.contrib.auth.models import User, Group
from .models import Incidencia, Comentario, Perfil, Edificio, Tecnico

class RegistroForm(forms.ModelForm):
    username = forms.CharField(label="Usuario", max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de usuario'}))
    first_name = forms.CharField(label="Nombre", max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu nombre'}))
    last_name = forms.CharField(label="Apellido", max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu apellido'}))
    email = forms.EmailField(label="Correo electrónico", widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejemplo@correo.com'}))
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña segura'}))
    confirm_password = forms.CharField(label="Confirmar Contraseña", widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repite la contraseña'}))

    edificio = forms.ModelChoiceField(queryset=Edificio.objects.all(), empty_label="Selecciona un edificio", widget=forms.Select(attrs={'class': 'form-select'}))
    piso = forms.CharField(label="Piso", max_length=10, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 3'}))
    puerta = forms.CharField(label="Puerta / Depto", max_length=10, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 302 o B'}))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Las contraseñas no coinciden.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            # Asignar grupo Residente
            grupo_residente, _ = Group.objects.get_or_create(name='Residente')
            user.groups.add(grupo_residente)

            # Crear perfil
            Perfil.objects.create(
                user=user,
                edificio=self.cleaned_data["edificio"],
                piso=self.cleaned_data["piso"],
                puerta=self.cleaned_data["puerta"]
            )
        return user


class IncidenciaResidenteForm(forms.ModelForm):
    class Meta:
        model = Incidencia
        fields = ['titulo', 'categoria', 'prioridad', 'descripcion', 'foto']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Fuga de agua en el baño'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe detalladamente la incidencia...'}),
            'foto': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean_titulo(self):
        titulo = self.cleaned_data.get('titulo', '').strip()
        if len(titulo) < 10:
            raise forms.ValidationError("El título debe tener al menos 10 caracteres para ser descriptivo.")
        return titulo

    def clean_foto(self):
        foto = self.cleaned_data.get('foto')
        if foto and hasattr(foto, 'size'):
            # 2 MB = 2 * 1024 * 1024 bytes
            limite_mb = 2
            if foto.size > limite_mb * 1024 * 1024:
                raise forms.ValidationError(f"El tamaño de la imagen no puede superar los {limite_mb}MB.")
        return foto


class IncidenciaAdminForm(forms.ModelForm):
    tecnico = forms.ModelChoiceField(
        queryset=Tecnico.objects.filter(activo=True),
        required=False,
        label="Seleccionar Técnico Registrado (por disponibilidad)",
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="-- Seleccionar técnico del catálogo (opcional) --"
    )

    class Meta:
        model = Incidencia
        fields = ['estado', 'prioridad', 'tecnico', 'tecnico_asignado', 'nota_interna']
        widgets = {
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'tecnico_asignado': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'O escribir nombre/empresa externa del técnico'
            }),
            'nota_interna': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Notas privadas visibles únicamente por administradores...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Custom label for each technician showing specialty and availability
        self.fields['tecnico'].label_from_instance = lambda obj: (
            f"{obj.nombre} — {obj.get_especialidad_display()} [{obj.get_disponibilidad_display()}]"
        )
        if self.instance and self.instance.pk and self.instance.tecnico:
            self.fields['tecnico'].initial = self.instance.tecnico

    def clean(self):
        cleaned_data = super().clean()
        tecnico = cleaned_data.get('tecnico')
        tecnico_asignado = cleaned_data.get('tecnico_asignado')

        if tecnico and not tecnico_asignado:
            cleaned_data['tecnico_asignado'] = tecnico.nombre
        return cleaned_data


class TecnicoForm(forms.ModelForm):
    class Meta:
        model = Tecnico
        fields = ['nombre', 'especialidad', 'disponibilidad', 'telefono', 'email', 'edificio', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Carlos Martínez'}),
            'especialidad': forms.Select(attrs={'class': 'form-select'}),
            'disponibilidad': forms.Select(attrs={'class': 'form-select'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+57 300 123 4567'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'carlos@tecnicos.com'}),
            'edificio': forms.Select(attrs={'class': 'form-select'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['mensaje']
        widgets = {
            'mensaje': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Escribe un comentario o actualización sobre esta incidencia...'
            })
        }
        labels = {
            'mensaje': ''
        }
