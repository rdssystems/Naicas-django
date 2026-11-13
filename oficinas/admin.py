from django.contrib import admin
from core import acesso
from core.admin import ArquivoSomenteLeituraAdmin
from .models import AtividadeCronograma, Oficina


@admin.register(Oficina)
class OficinaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cor', 'arquivada')
    list_filter = ('arquivada',)
    search_fields = ('nome',)

    def has_add_permission(self, request):
        return acesso.is_diretor(request.user)

    def has_change_permission(self, request, obj=None):
        return acesso.is_diretor(request.user)

    def has_delete_permission(self, request, obj=None):
        return acesso.is_diretor(request.user)


@admin.register(AtividadeCronograma)
class AtividadeCronogramaAdmin(ArquivoSomenteLeituraAdmin):
    list_display = ('nome', 'escola', 'turno', 'horario', 'ativo')
    list_filter = ('escola', 'turno', 'ativo')
