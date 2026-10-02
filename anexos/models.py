import uuid

from django.conf import settings
from django.db import models

from .validators import FORMATOS, extensao


class TipoDocumento(models.Model):
    nome = models.CharField('nome', max_length=150, unique=True)
    obrigatorio = models.BooleanField('obrigatório', default=False)
    # Tipo em uso não é excluído (preserva os anexos), só desativado.
    ativo = models.BooleanField('ativo', default=True)
    ordem = models.PositiveSmallIntegerField('ordem', default=0, help_text='Menor aparece primeiro.')

    class Meta:
        verbose_name = 'tipo de documento'
        verbose_name_plural = 'tipos de documento'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return self.nome


def caminho_anexo(instance, filename):
    # Sem o nome original no caminho (pode conter dado pessoal); ele fica em nome_original.
    return f'anexos/aluno_{instance.aluno_id}/{uuid.uuid4().hex}.{extensao(filename)}'


class Anexo(models.Model):
    aluno = models.ForeignKey('alunos.Aluno', on_delete=models.CASCADE, related_name='anexos')
    tipo_documento = models.ForeignKey(
        TipoDocumento, verbose_name='tipo de documento', on_delete=models.PROTECT, related_name='anexos',
    )
    arquivo = models.FileField('arquivo', upload_to=caminho_anexo)
    nome_original = models.CharField('nome do arquivo', max_length=255)
    tamanho = models.PositiveIntegerField('tamanho (bytes)')
    data_envio = models.DateTimeField('enviado em', auto_now_add=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='enviado por', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    class Meta:
        verbose_name = 'anexo'
        verbose_name_plural = 'anexos'
        ordering = ['tipo_documento__ordem', 'data_envio']

    def __str__(self):
        return f'{self.tipo_documento} — {self.nome_original}'

    @property
    def content_type(self):
        return FORMATOS.get(extensao(self.arquivo.name), ('application/octet-stream', None))[0]

    @property
    def e_imagem(self):
        return self.content_type.startswith('image/')
