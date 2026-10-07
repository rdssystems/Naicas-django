from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from core import acesso
from core.acesso import NivelAcesso
from escolas.models import EscolaNaica

from .models import Oficina, TipoOficina


class TipoOficinaForm(forms.ModelForm):
    """Diretor escolhe a unidade; para o Coordenador ela é sempre a dele."""

    class Meta:
        model = TipoOficina
        fields = ['escola', 'nome', 'cor']
        widgets = {'cor': forms.TextInput(attrs={'type': 'color'})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if acesso.is_coordenador(user):
            del self.fields['escola']
            self.instance.escola = acesso.escola_do_usuario(user)
        else:
            self.fields['escola'].queryset = EscolaNaica.objects.all()
            if not self.instance.pk and (foco := acesso.escola_em_foco(user)):
                self.initial.setdefault('escola', foco.pk)
        if not self.instance.pk:
            # input type=color não tem "vazio"; começa no azul do tema.
            self.initial.setdefault('cor', '#0d6efd')
        if acesso.is_diretor(user):
            if self.instance.pk and self.instance.oficinas.exists():
                # Mudar a unidade do tipo "moveria" as oficinas dele de unidade.
                self.fields['escola'].disabled = True
                self.fields['escola'].help_text = 'Não pode mudar: já há oficinas com este tipo.'

    def clean(self):
        cleaned = super().clean()
        # Quando 'escola' está fora do form (Coordenador), o Django pula a
        # UniqueConstraint (escola, nome); checa aqui para não estourar no banco.
        escola = cleaned.get('escola') or self.instance.escola
        nome = cleaned.get('nome')
        if escola and nome:
            duplicado = TipoOficina.objects.filter(escola=escola, nome__iexact=nome).exclude(
                pk=self.instance.pk
            )
            if duplicado.exists():
                self.add_error('nome', 'Já existe um tipo com esse nome nesta unidade.')
        return cleaned


class OficinaForm(forms.ModelForm):
    dias_semana = forms.TypedMultipleChoiceField(
        label='Dias da semana',
        choices=Oficina.DiaSemana.choices,
        coerce=int,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = Oficina
        fields = [
            'tipo_oficina', 'nome', 'carga_horaria', 'vagas',
            'data_inicio', 'data_fim', 'dias_semana', 'turno', 'horario', 'horario_fim',
            'status', 'monitores', 'nome_monitor', 'telefone_monitor',
        ]
        widgets = {
            'data_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'data_fim': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'horario': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'horario_fim': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'monitores': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        tipos = acesso.filtrar_por_escola(user, TipoOficina.objects.select_related('escola'))
        if self.instance.pk:
            # Na edição a oficina não muda de unidade: só tipos da unidade dela.
            tipos = tipos.filter(escola_id=self.instance.escola_id)
            self.initial['dias_semana'] = self.instance.dias_semana
        campo_tipo = self.fields['tipo_oficina']
        campo_tipo.queryset = tipos
        if acesso.is_diretor(user) and not self.instance.pk:
            campo_tipo.label_from_instance = lambda t: f'{t.escola.nome} · {t.nome}'
            campo_tipo.help_text = 'A unidade da oficina é a unidade do tipo escolhido.'

        # Monitores são globais: qualquer Monitor ativo pode ser designado.
        # Os já designados continuam na lista mesmo se forem desativados depois.
        filtro_monitores = Q(is_active=True)
        if self.instance.pk:
            filtro_monitores |= Q(pk__in=list(self.instance.monitores.values_list('pk', flat=True)))
        campo_monitores = self.fields['monitores']
        campo_monitores.queryset = (
            User.objects.filter(profile__nivel_acesso=NivelAcesso.MONITOR)
            .filter(filtro_monitores)
            .order_by('first_name', 'username')
        )
        campo_monitores.label_from_instance = lambda u: u.get_full_name() or u.username
        campo_monitores.help_text = 'Monitores da rede que lançam a frequência desta oficina.'
