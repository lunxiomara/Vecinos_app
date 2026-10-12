import django_filters
from django import forms
from .models import Incidencia

class IncidenciaFilter(django_filters.FilterSet):
    titulo = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Buscar por título',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. agua, ascensor...'})
    )
    categoria = django_filters.ChoiceFilter(
        choices=Incidencia.CATEGORIAS,
        label='Categoría',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    estado = django_filters.ChoiceFilter(
        choices=Incidencia.ESTADOS,
        label='Estado',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    prioridad = django_filters.ChoiceFilter(
        choices=Incidencia.PRIORIDADES,
        label='Prioridad',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Incidencia
        fields = ['titulo', 'categoria', 'estado', 'prioridad']
