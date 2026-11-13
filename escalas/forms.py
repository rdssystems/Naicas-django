from django import forms

from core import acesso
from escolas.models import EscolaNaica
from oficinas.models import AtividadeCronograma


class FiltrosCronogramaDiretorForm(forms.Form):
    escola = forms.ModelChoiceField(
        label='Naica', queryset=EscolaNaica.objects.none(), empty_label='Selecione o Naica',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    turno = forms.ChoiceField(
        label='Turno', choices=[('', 'Selecione o turno'), *AtividadeCronograma.Turno.choices],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['escola'].queryset = acesso.filtrar_por_escola(
            user, EscolaNaica.objects.all(), campo='pk',
        )
        self.fields['escola'].initial = acesso.escola_ativa(user)
