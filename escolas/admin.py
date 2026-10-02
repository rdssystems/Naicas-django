from django.contrib import admin

from .models import EscolaNaica


@admin.register(EscolaNaica)
class EscolaNaicaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'telefone', 'email', 'coordenador_user')
    search_fields = ('nome',)
    readonly_fields = ('slug',)
