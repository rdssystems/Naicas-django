from django.contrib import admin

from .models import Anexo, TipoDocumento


@admin.register(TipoDocumento)
class TipoDocumentoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'obrigatorio', 'ativo', 'ordem')
    list_editable = ('obrigatorio', 'ativo', 'ordem')


@admin.register(Anexo)
class AnexoAdmin(admin.ModelAdmin):
    list_display = ('aluno', 'tipo_documento', 'nome_original', 'data_envio', 'enviado_por')
    list_filter = ('tipo_documento',)
    search_fields = ('aluno__nome', 'nome_original')
    readonly_fields = ('nome_original', 'tamanho', 'data_envio', 'enviado_por')
