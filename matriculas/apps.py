from django.apps import AppConfig


class MatriculasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'matriculas'
    verbose_name = 'Matrículas'

    def ready(self):
        from alunos.etapas import Etapa, registrar
        from alunos.visibilidade import registrar_criterio_coordenador

        # Consulta do cronograma; não exige matrícula individual em oficinas.
        registrar(Etapa(
            6, 'Cronograma', 'matriculas:aluno',
            lambda aluno: bool(aluno.turno and aluno.turma),
            conta_para_completo=False,
        ))
        # Coordenador também enxerga alunos matriculados em oficinas da unidade dele.
        registrar_criterio_coordenador(_matriculado_na_unidade)


def _matriculado_na_unidade(escola):
    from django.db.models import Q

    return Q(matriculas__escola=escola)
