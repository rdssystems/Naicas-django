from django.contrib import admin

from .models import Aluno, AlunoResponsavel, Endereco, Responsavel


class EnderecoInline(admin.StackedInline):
    model = Endereco
    can_delete = False


class AlunoResponsavelInline(admin.TabularInline):
    model = AlunoResponsavel
    extra = 0
    autocomplete_fields = ('responsavel',)


@admin.register(Aluno)
class AlunoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cpf', 'escola', 'data_nascimento', 'ano_escolar')
    list_filter = ('escola', 'ano_escolar', 'sexo')
    search_fields = ('nome', 'cpf', 'nome_mae')
    inlines = [EnderecoInline, AlunoResponsavelInline]
    readonly_fields = ('criado_em', 'atualizado_em', 'criado_por')


@admin.register(Responsavel)
class ResponsavelAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cpf', 'celular')
    search_fields = ('nome', 'cpf')
