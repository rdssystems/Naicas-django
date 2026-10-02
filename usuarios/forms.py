from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from core.acesso import NivelAcesso
from escolas.models import EscolaNaica

from .models import Profile


class UsuarioForm(forms.ModelForm):
    """
    Cadastro/edição de usuário pelo Diretor (único papel que gerencia contas).
    Na criação a senha é obrigatória; na edição, só se for trocar.
    """

    nivel_acesso = forms.ChoiceField(label='Nível de acesso', choices=NivelAcesso.choices)
    escola = forms.ModelChoiceField(
        label='Unidade',
        queryset=EscolaNaica.objects.all(),
        required=False,
        help_text='Obrigatória só para Coordenador. Monitores são da rede inteira.',
    )
    senha = forms.CharField(label='Senha', widget=forms.PasswordInput, required=False)
    senha_confirmacao = forms.CharField(
        label='Confirme a senha', widget=forms.PasswordInput, required=False
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        labels = {
            'username': 'Nome de usuário',
            'first_name': 'Nome',
            'last_name': 'Sobrenome',
            'email': 'E-mail',
        }

    def __init__(self, *args, usuario_logado=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario_logado = usuario_logado
        self.fields['first_name'].required = True
        self.is_criacao = self.instance.pk is None
        if self.is_criacao:
            self.fields['senha'].required = True
            self.fields['senha_confirmacao'].required = True
        else:
            self.fields['senha'].label = 'Nova senha'
            self.fields['senha'].help_text = 'Deixe em branco para manter a senha atual.'
            profile = getattr(self.instance, 'profile', None)
            if profile:
                self.initial['nivel_acesso'] = profile.nivel_acesso
                self.initial['escola'] = profile.escola_id

    def clean(self):
        cleaned = super().clean()
        nivel = cleaned.get('nivel_acesso')
        editando_a_si_mesmo = (
            self.usuario_logado is not None and self.instance.pk == self.usuario_logado.pk
        )
        if editando_a_si_mesmo and nivel != NivelAcesso.DIRETOR:
            self.add_error(
                'nivel_acesso', 'Você não pode alterar o seu próprio nível de acesso.'
            )
        if nivel == NivelAcesso.COORDENADOR:
            if not cleaned.get('escola'):
                self.add_error('escola', 'Coordenador precisa estar vinculado a uma unidade.')
        else:
            cleaned['escola'] = None

        senha = cleaned.get('senha')
        if (senha or cleaned.get('senha_confirmacao')) and senha != cleaned.get('senha_confirmacao'):
            self.add_error('senha_confirmacao', 'As senhas não conferem.')
        return cleaned

    def _post_clean(self):
        super()._post_clean()
        # Aqui self.instance já tem username/nome preenchidos, o que o
        # UserAttributeSimilarityValidator precisa (mesmo padrão do UserCreationForm).
        senha = self.cleaned_data.get('senha')
        if senha and 'senha_confirmacao' not in self.errors:
            try:
                validate_password(senha, self.instance)
            except forms.ValidationError as e:
                self.add_error('senha', e)

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('senha'):
            user.set_password(self.cleaned_data['senha'])
        user.save()
        profile = getattr(user, 'profile', None) or Profile(user=user)
        profile.nivel_acesso = self.cleaned_data['nivel_acesso']
        profile.escola = self.cleaned_data['escola']
        profile.full_clean()
        profile.save()
        # Deixou de ser Coordenador (ou mudou de unidade): sai de responsável
        # das unidades que não são mais a dele.
        EscolaNaica.objects.filter(coordenador_user=user).exclude(
            pk=profile.escola_id if profile.nivel_acesso == NivelAcesso.COORDENADOR else None
        ).update(coordenador_user=None)
        return user
