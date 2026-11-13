from django.contrib import admin


class ArquivoSomenteLeituraAdmin(admin.ModelAdmin):
    """Histórico preservado: toda escrita acontece nos fluxos atuais do sistema."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
