from django.contrib import admin

from core.admin import ArquivoSomenteLeituraAdmin
from .models import Chamada, ChamadaGeral, RegistroAula


class ChamadaInline(admin.TabularInline):
    model = Chamada
    extra = 0
    raw_id_fields = ('matricula',)
    can_delete = False
    readonly_fields = ('matricula', 'status_presenca', 'observacoes')

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RegistroAula)
class RegistroAulaAdmin(ArquivoSomenteLeituraAdmin):
    list_display = ('oficina', 'data_aula', 'lancado_por', 'atualizado_por')
    list_filter = ('oficina__escola',)
    date_hierarchy = 'data_aula'
    inlines = [ChamadaInline]
    readonly_fields = ('lancado_por', 'lancado_em', 'atualizado_por', 'atualizado_em')


@admin.register(ChamadaGeral)
class ChamadaGeralAdmin(ArquivoSomenteLeituraAdmin):
    list_display = ('aluno', 'escola', 'data', 'status_presenca', 'lancado_por')
    list_filter = ('escola', 'status_presenca')
    date_hierarchy = 'data'
    search_fields = ('aluno__nome',)
