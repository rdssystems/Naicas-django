from django import forms

from .validators import so_digitos

SIM_NAO = [('True', 'Sim'), ('False', 'Não')]


class DigitosField(forms.CharField):
    """Aceita o valor com máscara (000.000.000-00) e entrega só os dígitos."""

    def to_python(self, value):
        return so_digitos(super().to_python(value))


def sim_nao_field(label, required=True):
    """Pergunta Sim/Não em rádio. Opcional => None quando não respondida."""
    return forms.TypedChoiceField(
        label=label,
        choices=SIM_NAO,
        coerce=lambda v: v == 'True',
        empty_value=None,
        required=required,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
    )
