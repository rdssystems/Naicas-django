from django import forms
from django.contrib.auth.models import User

from core.acesso import NivelAcesso

from .models import EscolaNaica


class EscolaNaicaForm(forms.ModelForm):
    class Meta:
        model = EscolaNaica
        fields = ['nome', 'endereco', 'telefone', 'email', 'coordenador_user']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campo = self.fields['coordenador_user']
        if self.instance.pk:
            # Só Coordenadores ativos desta unidade podem ser o responsável.
            campo.queryset = User.objects.filter(
                is_active=True,
                profile__nivel_acesso=NivelAcesso.COORDENADOR,
                profile__escola=self.instance,
            ).order_by('first_name', 'username')
            campo.label_from_instance = lambda u: u.get_full_name() or u.username
        else:
            # Na criação ainda não há Coordenador vinculado à unidade nova.
            del self.fields['coordenador_user']
