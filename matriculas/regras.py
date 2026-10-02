"""
Regras de matrícula. Toda criação/alteração de matrícula passa por aqui
(telas do aluno e da oficina usam as mesmas funções).
"""

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from core import acesso
from oficinas.models import Oficina

from .models import Matricula

STATUS_ABERTOS = (Oficina.Status.ABERTA, Oficina.Status.EM_ANDAMENTO)


class MatriculaRecusada(Exception):
    """Motivo legível para o usuário."""


def com_vagas_ocupadas(queryset):
    return queryset.annotate(
        vagas_ocupadas=Count('matriculas', filter=Q(matriculas__status=Matricula.Status.CURSANDO))
    )


def vagas_ocupadas(oficina):
    return oficina.matriculas.filter(status=Matricula.Status.CURSANDO).count()


def horarios_se_chocam(a, b):
    """Dia da semana em comum + horários sobrepostos + períodos que se cruzam."""
    return (
        bool(set(a.dias_semana) & set(b.dias_semana))
        and a.horario < b.horario_fim and b.horario < a.horario_fim
        and a.data_inicio <= b.data_fim and b.data_inicio <= a.data_fim
    )


def conflitos_de_horario(aluno, oficina):
    """Matrículas 'cursando' do aluno em outras oficinas que chocam com esta."""
    outras = Matricula.objects.filter(aluno=aluno, status=Matricula.Status.CURSANDO).exclude(
        oficina=oficina
    ).select_related('oficina')
    return [m for m in outras if horarios_se_chocam(m.oficina, oficina)]


def oficinas_para_matricular(user):
    """Oficinas abertas que o usuário pode receber matrícula, com vagas_ocupadas."""
    qs = acesso.filtrar_por_escola(
        user, Oficina.objects.filter(status__in=STATUS_ABERTOS).select_related('escola')
    )
    return com_vagas_ocupadas(qs).order_by('escola__nome', 'nome')


@transaction.atomic
def matricular(aluno, oficina, user):
    # Trava a oficina até o fim da transação: duas matrículas simultâneas na
    # última vaga não passam as duas pela contagem.
    oficina = Oficina.objects.select_for_update().get(pk=oficina.pk)

    if not acesso.pode_gerenciar_escola(user, oficina.escola_id):
        raise MatriculaRecusada('Você não pode matricular alunos nesta oficina.')
    if oficina.status not in STATUS_ABERTOS:
        raise MatriculaRecusada(f'A oficina está "{oficina.get_status_display()}" e não aceita matrículas.')
    if Matricula.objects.filter(aluno=aluno, oficina=oficina, status=Matricula.Status.CURSANDO).exists():
        raise MatriculaRecusada(f'{aluno.nome} já está cursando esta oficina.')
    if vagas_ocupadas(oficina) >= oficina.vagas:
        raise MatriculaRecusada(f'A oficina "{oficina.nome}" está sem vagas ({oficina.vagas} ocupadas).')
    if conflitos := conflitos_de_horario(aluno, oficina):
        nomes = ', '.join(f'"{m.oficina.nome}"' for m in conflitos)
        raise MatriculaRecusada(f'Choque de horário com {nomes}, que {aluno.nome} já cursa.')

    return Matricula.objects.create(aluno=aluno, oficina=oficina, matriculado_por=user)


def _checar_gestao(matricula, user):
    if not acesso.pode_gerenciar_escola(user, matricula.escola_id):
        raise MatriculaRecusada('Você não pode alterar esta matrícula.')
    if matricula.status != Matricula.Status.CURSANDO:
        raise MatriculaRecusada('Só matrículas em curso podem ser concluídas ou encerradas.')


def concluir(matricula, user, data=None):
    _checar_gestao(matricula, user)
    matricula.status = Matricula.Status.CONCLUIDO
    matricula.data_conclusao = data or timezone.localdate()
    matricula.save(update_fields=['status', 'data_conclusao'])


def registrar_desistencia(matricula, user, data=None):
    _checar_gestao(matricula, user)
    matricula.status = Matricula.Status.DESISTENTE
    matricula.data_desistencia = data or timezone.localdate()
    matricula.save(update_fields=['status', 'data_desistencia'])
