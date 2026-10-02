from django.apps import AppConfig


class AnexosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'anexos'
    verbose_name = 'Anexos'

    def ready(self):
        from alunos.etapas import Etapa, registrar
        from django.db.models.signals import post_delete

        from .etapa import documentos_obrigatorios_ok
        from .models import Anexo

        registrar(Etapa(5, 'Anexos', 'anexos:aluno', documentos_obrigatorios_ok, prefetch=('anexos',)))

        # Apaga o arquivo do disco junto com o registro (inclusive em exclusão
        # em cascata do aluno). Sem isso o arquivo ficaria órfão no storage.
        post_delete.connect(_apagar_arquivo, sender=Anexo, dispatch_uid='anexos_apagar_arquivo')


def _apagar_arquivo(sender, instance, **kwargs):
    if instance.arquivo:
        instance.arquivo.delete(save=False)
