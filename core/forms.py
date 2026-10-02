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


class MoedaField(forms.DecimalField):
    """
    Valor em reais aceitando o formato brasileiro ("1.518,50") e o simples
    ("1518.50"). Não usa USE_THOUSAND_SEPARATOR, que afetaria todo número
    exibido no sistema.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault('max_digits', 10)
        kwargs.setdefault('decimal_places', 2)
        kwargs.setdefault('widget', forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': '0,00'}))
        super().__init__(**kwargs)

    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip().replace('R$', '').strip()
            if ',' in value:
                value = value.replace('.', '').replace(',', '.')
        return super().to_python(value)

    def prepare_value(self, value):
        # Mostra no formulário como "1518,50".
        if value not in (None, '') and not isinstance(value, str):
            return f'{value:.2f}'.replace('.', ',')
        return value
