from django.apps import AppConfig


class MatriculasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'matriculas'
    verbose_name = 'Matrículas'

    def ready(self):
        from alunos.etapas import Etapa, registrar
        from alunos.visibilidade import registrar_criterio_coordenador

        # Etapa 6 do cadastro: não conta para o selo (aluno completo pode
        # estar na fila de espera, sem matrícula).
        registrar(Etapa(
            6, 'Matrícula', 'matriculas:aluno',
            lambda aluno: any(m.status == 'CURSANDO' for m in aluno.matriculas.all()),
            conta_para_completo=False, prefetch=('matriculas',),
        ))
        # Coordenador também enxerga alunos matriculados em oficinas da unidade dele.
        registrar_criterio_coordenador(_matriculado_na_unidade)


def _matriculado_na_unidade(escola):
    from django.db.models import Q

    return Q(matriculas__escola=escola)
