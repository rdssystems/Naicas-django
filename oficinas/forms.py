from django import forms
from django.db.models import Q

from core import acesso
from escolas.models import EscolaNaica

from .models import AtividadeCronograma, Oficina


class OficinaForm(forms.ModelForm):
    class Meta:
        model = Oficina
        fields = ['nome', 'cor']
        widgets = {'cor': forms.TextInput(attrs={'type': 'color'})}

    def clean_nome(self):
        nome = self.cleaned_data['nome'].strip()
        if Oficina.objects.filter(nome__iexact=nome).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Já existe uma oficina com esse nome no catálogo da rede.')
        return nome


class AtividadeCronogramaForm(forms.ModelForm):
    turmas = forms.MultipleChoiceField(
        label='Turmas', choices=AtividadeCronograma.Turma.choices,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
    )
    dias_semana = forms.TypedMultipleChoiceField(
        label='Dias da semana', choices=AtividadeCronograma.DiaSemana.choices, coerce=int,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = AtividadeCronograma
        fields = ['escola', 'oficina', 'instrutor_nome', 'turmas', 'turno', 'dias_semana', 'horario', 'horario_fim']
        widgets = {
            'horario': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'horario_fim': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['oficina'].required = True
        self.fields['oficina'].queryset = Oficina.objects.filter(
            Q(arquivada=False) | Q(pk=self.instance.oficina_id),
        )
        self.fields['oficina'].help_text = 'Escolha uma oficina do catálogo criado pelo Diretor.'
        self.fields['instrutor_nome'].help_text = 'Nome do instrutor que aparecerá no card deste horário.'
        if self.instance.pk:
            # Editar um horário não transfere seus históricos de unidade.
            self.fields.pop('escola')
        elif unidade := acesso.escola_ativa(user):
            self.fields.pop('escola')
            self.instance.escola = unidade
        else:
            self.fields['escola'].queryset = acesso.filtrar_por_escola(
                user, EscolaNaica.objects.all(), campo='pk',
            )

    def clean_turmas(self):
        return sorted(set(self.cleaned_data['turmas']))

    def clean_dias_semana(self):
        return sorted(set(self.cleaned_data['dias_semana']))
