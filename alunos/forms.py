from django import forms

from core import acesso
from core.forms import DigitosField, MoedaField, sim_nao_field
from escolas.models import EscolaNaica

from .models import Aluno, AlunoResponsavel, ContatoEmergencia, Endereco, MembroFamiliar, Parentesco, Responsavel

DATA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class AlunoForm(forms.ModelForm):
    cpf = DigitosField(label='CPF', max_length=14, widget=forms.TextInput(attrs={'inputmode': 'numeric', 'placeholder': '000.000.000-00'}))
    nis = DigitosField(label='NIS', max_length=14, required=False, widget=forms.TextInput(attrs={'inputmode': 'numeric'}))

    class Meta:
        model = Aluno
        fields = [
            'escola', 'cpf', 'nome', 'nome_mae', 'data_nascimento', 'sexo',
            'naturalidade', 'nis', 'nome_escola', 'ano_escolar',
        ]
        widgets = {'data_nascimento': DATA}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Preenchido quando o CPF já existe; a view usa para mostrar o link
        # (se o usuário enxerga o aluno) ou só o aviso (se é de outra unidade).
        self.aluno_existente = None
        if acesso.is_coordenador(user):
            del self.fields['escola']
            if not self.instance.pk:
                self.instance.escola = acesso.escola_do_usuario(user)
        else:
            self.fields['escola'].queryset = EscolaNaica.objects.all()
            self.fields['escola'].help_text = 'Unidade responsável pelo cadastro deste aluno.'

    def clean_cpf(self):
        cpf = self.cleaned_data['cpf']
        existente = (
            Aluno.objects.select_related('escola').filter(cpf=cpf).exclude(pk=self.instance.pk).first()
        )
        if existente:
            self.aluno_existente = existente
            if Aluno.objects.visiveis_para(self.user).filter(pk=existente.pk).exists():
                raise forms.ValidationError('Este CPF já está cadastrado.')
            raise forms.ValidationError(
                f'Este aluno já está cadastrado na unidade {existente.escola}. '
                'Ele pode ser matriculado numa oficina da sua unidade pelo módulo de Matrículas.'
            )
        return cpf


class EnderecoForm(forms.ModelForm):
    cep = DigitosField(label='CEP', max_length=9, widget=forms.TextInput(attrs={'inputmode': 'numeric', 'placeholder': '00000-000'}))

    class Meta:
        model = Endereco
        fields = ['cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'estado']


class ResponsavelForm(forms.ModelForm):
    """
    Dados do responsável + grau de parentesco com ESTE aluno.
    Se o CPF já existe na rede, a view passa o cadastro existente como
    instance: salvar atualiza o mesmo responsável (não duplica).
    """

    cpf = DigitosField(label='CPF', max_length=14, widget=forms.TextInput(attrs={'inputmode': 'numeric', 'placeholder': '000.000.000-00'}))
    grau_parentesco = forms.ChoiceField(label='Grau de parentesco', choices=Parentesco.choices)
    trabalha = sim_nao_field('Trabalha?')
    carteira_assinada = sim_nao_field('Carteira assinada?', required=False)
    contribui_previdencia = sim_nao_field('Contribui com a Previdência?', required=False)
    recebe_beneficio = sim_nao_field('Recebe algum benefício?')

    class Meta:
        model = Responsavel
        fields = [
            'cpf', 'nome', 'data_nascimento', 'celular', 'email',
            'documento_numero', 'documento_data_expedicao', 'documento_orgao_expedidor', 'documento_uf',
            'trabalha', 'carteira_assinada', 'ctps_numero', 'ctps_serie',
            'contribui_previdencia', 'recebe_beneficio', 'qual_beneficio',
        ]
        widgets = {'data_nascimento': DATA, 'documento_data_expedicao': DATA}

    def __init__(self, *args, aluno, vinculo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.aluno = aluno
        self.vinculo = vinculo
        if vinculo:
            self.initial['grau_parentesco'] = vinculo.grau_parentesco

    def clean(self):
        cleaned = super().clean()
        if self.vinculo is None and self.instance.pk:
            if AlunoResponsavel.objects.filter(aluno=self.aluno, responsavel=self.instance).exists():
                raise forms.ValidationError('Este responsável já está vinculado ao aluno.')
        return cleaned

    def save(self, commit=True):
        responsavel = super().save()
        if self.vinculo:
            self.vinculo.grau_parentesco = self.cleaned_data['grau_parentesco']
            self.vinculo.save(update_fields=['grau_parentesco'])
        else:
            AlunoResponsavel.objects.create(
                aluno=self.aluno, responsavel=responsavel,
                grau_parentesco=self.cleaned_data['grau_parentesco'],
            )
        return responsavel


class MembroFamiliarForm(forms.ModelForm):
    renda_mensal = MoedaField(label='Renda mensal (R$)', min_value=0, required=False)

    class Meta:
        model = MembroFamiliar
        fields = ['responsavel', 'nome', 'parentesco', 'data_nascimento', 'ocupacao', 'renda_mensal']
        widgets = {'data_nascimento': DATA, 'responsavel': forms.HiddenInput}

    def __init__(self, *args, aluno, **kwargs):
        super().__init__(*args, **kwargs)
        # Só responsáveis deste aluno podem ser a origem de uma linha.
        self.fields['responsavel'].queryset = Responsavel.objects.filter(alunos_vinculos__aluno=aluno)

    def clean_renda_mensal(self):
        return self.cleaned_data['renda_mensal'] or 0


MembroFamiliarFormSet = forms.inlineformset_factory(
    Aluno, MembroFamiliar, form=MembroFamiliarForm, extra=0, can_delete=True,
)

ContatoEmergenciaFormSet = forms.inlineformset_factory(
    Aluno, ContatoEmergencia,
    fields=['nome', 'parentesco', 'celular'],
    extra=0, min_num=2, validate_min=True, can_delete=True,
)
