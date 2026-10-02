from django import forms

from .models import TipoDocumento
from .validators import EXTENSOES_ACEITAS, validar_arquivo


class EnvioAnexoForm(forms.Form):
    tipo_documento = forms.ModelChoiceField(
        label='Tipo de documento', queryset=TipoDocumento.objects.filter(ativo=True),
    )
    arquivo = forms.FileField(
        label='Arquivo',
        help_text=f'{EXTENSOES_ACEITAS}, até 10 MB.',
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/*'}),
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data['arquivo']
        validar_arquivo(arquivo)
        return arquivo


class TipoDocumentoForm(forms.ModelForm):
    class Meta:
        model = TipoDocumento
        fields = ['nome', 'obrigatorio', 'ativo', 'ordem']
        help_texts = {
            'obrigatorio': 'Sem ele o aluno não recebe o selo "Cadastro completo".',
            'ativo': 'Desativado: some do envio e deixa de ser exigido, mas os arquivos já enviados continuam.',
        }
