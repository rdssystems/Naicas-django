from django.contrib import admin

from .models import Designacao, Oficina, TipoOficina


@admin.register(TipoOficina)
class TipoOficinaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'escola', 'cor')
    list_filter = ('escola',)
    search_fields = ('nome',)


class DesignacaoInline(admin.TabularInline):
    model = Designacao
    extra = 0
    raw_id_fields = ('monitor',)


@admin.register(Oficina)
class OficinaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'escola', 'tipo_oficina', 'turno', 'status', 'data_inicio', 'data_fim')
    list_filter = ('escola', 'status', 'turno')
    search_fields = ('nome',)
    inlines = [DesignacaoInline]
