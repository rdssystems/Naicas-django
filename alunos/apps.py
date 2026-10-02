from django.apps import AppConfig


class AlunosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'alunos'
    verbose_name = 'Alunos'

    def ready(self):
        from .etapas import registrar_etapas_do_cadastro

        registrar_etapas_do_cadastro()
