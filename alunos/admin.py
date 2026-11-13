from django.contrib import admin

from .models import Aluno, AlunoResponsavel, ContatoEmergencia, Endereco, FichaSaude, MembroFamiliar, Responsavel


class EnderecoInline(admin.StackedInline):
    model = Endereco
    can_delete = False


class AlunoResponsavelInline(admin.TabularInline):
    model = AlunoResponsavel
    extra = 0
    autocomplete_fields = ('responsavel',)


class MembroFamiliarInline(admin.TabularInline):
    model = MembroFamiliar
    extra = 0


class ContatoEmergenciaInline(admin.TabularInline):
    model = ContatoEmergencia
    extra = 0


class FichaSaudeInline(admin.StackedInline):
    model = FichaSaude
    can_delete = False
    readonly_fields = ('atualizado_em', 'atualizado_por')


@admin.register(Aluno)
class AlunoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cpf', 'escola', 'status', 'data_nascimento', 'ano_escolar')
    list_filter = ('escola', 'status', 'ano_escolar', 'sexo')
    search_fields = ('nome', 'cpf', 'nome_mae')
    inlines = [EnderecoInline, AlunoResponsavelInline, MembroFamiliarInline, ContatoEmergenciaInline, FichaSaudeInline]
    readonly_fields = ('criado_em', 'atualizado_em', 'criado_por')


@admin.register(Responsavel)
class ResponsavelAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cpf', 'celular')
    search_fields = ('nome', 'cpf')
