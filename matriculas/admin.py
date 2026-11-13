from django.contrib import admin
from core.admin import ArquivoSomenteLeituraAdmin

from .models import Matricula


@admin.register(Matricula)
class MatriculaAdmin(ArquivoSomenteLeituraAdmin):
    list_display = ('aluno', 'oficina', 'escola', 'status', 'data_inscricao')
    list_filter = ('status', 'escola')
    search_fields = ('aluno__nome', 'aluno__cpf', 'oficina__nome')
    readonly_fields = ('escola', 'turno', 'data_inscricao', 'matriculado_por')
