from django import forms
from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import ExtractYear

from alunos.models import Aluno
from core import acesso
from escolas.models import EscolaNaica


def com_idade(queryset, hoje):
    aniversario_pendente = (
        Q(data_nascimento__month__gt=hoje.month)
        | Q(data_nascimento__month=hoje.month, data_nascimento__day__gt=hoje.day)
    )
    return queryset.annotate(idade=hoje.year - ExtractYear('data_nascimento') - Case(
        When(aniversario_pendente, then=Value(1)), default=Value(0), output_field=IntegerField(),
    ))


class FiltrosAlunosForm(forms.Form):
    escola = forms.ModelChoiceField(
        label='Unidade', queryset=EscolaNaica.objects.order_by('nome'),
        required=False, empty_label='Todas as unidades',
    )
    idade_operador = forms.ChoiceField(
        label='Idade', required=False, initial='gt',
        choices=[('gt', 'Mais de'), ('gte', 'No mínimo'), ('eq', 'Exatamente'),
                 ('lte', 'No máximo'), ('lt', 'Menos de')],
    )
    idade = forms.IntegerField(
        label='Anos', required=False, min_value=0, max_value=150,
        widget=forms.NumberInput(attrs={'placeholder': 'Qualquer idade'}),
    )
    mes_aniversario = forms.TypedChoiceField(
        label='Mês de aniversário', required=False, coerce=int, empty_value=None,
        choices=[('', 'Todos os meses'), (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'),
                 (4, 'Abril'), (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
                 (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')],
    )
    sexo = forms.ChoiceField(
        label='Sexo', required=False, choices=[('', 'Todos'), *Aluno.Sexo.choices],
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        # O parâmetro de unidade nunca pode ampliar o escopo do usuário.
        if not acesso.is_diretor(user) or acesso.escola_ativa(user):
            self.fields.pop('escola')
        for campo in self.fields.values():
            campo.widget.attrs['class'] = (
                'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'
            )

    @property
    def ativos(self):
        dados = self.cleaned_data
        return any(dados.get(campo) not in (None, '') for campo in (
            'escola', 'idade', 'mes_aniversario', 'sexo',
        ))

    def filtrar_alunos(self, queryset, hoje):
        dados = self.cleaned_data
        if dados.get('idade') is not None:
            operador = dados.get('idade_operador') or 'gt'
            lookup = 'idade' if operador == 'eq' else f'idade__{operador}'
            queryset = com_idade(queryset, hoje).filter(**{lookup: dados['idade']})
        if mes := dados.get('mes_aniversario'):
            queryset = queryset.filter(data_nascimento__month=mes)
        if sexo := dados.get('sexo'):
            queryset = queryset.filter(sexo=sexo)
        return queryset

    def filtrar_recorte(self, recorte, hoje):
        recorte = recorte.copy()
        if escola := self.cleaned_data.get('escola'):
            recorte['escolas'] = recorte['escolas'].filter(pk=escola.pk)
            recorte['oficinas'] = recorte['oficinas'].filter(escola=escola)
            recorte['alunos'] = recorte['alunos'].da_unidade(escola)
        recorte['alunos'] = self.filtrar_alunos(recorte['alunos'], hoje)
        return recorte
