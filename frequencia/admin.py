from django.contrib import admin

from .models import Chamada, RegistroAula


class ChamadaInline(admin.TabularInline):
    model = Chamada
    extra = 0
    raw_id_fields = ('matricula',)


@admin.register(RegistroAula)
class RegistroAulaAdmin(admin.ModelAdmin):
    list_display = ('oficina', 'data_aula', 'lancado_por', 'atualizado_por')
    list_filter = ('oficina__escola',)
    date_hierarchy = 'data_aula'
    inlines = [ChamadaInline]
    readonly_fields = ('lancado_por', 'lancado_em', 'atualizado_por', 'atualizado_em')
