"""Regras da ficha de frequência (usadas pelas views e testes)."""

from django.db.models import Count, Q
from django.utils import timezone

from matriculas.models import Matricula
from oficinas.models import Oficina

from .models import Chamada


class DataInvalida(Exception):
    pass


def validar_data_aula(oficina, data):
    """Levanta DataInvalida; devolve aviso (str) se a data não é dia da oficina."""
    hoje = timezone.localdate()
    if oficina.status == Oficina.Status.ARQUIVADO:
        raise DataInvalida('Oficina arquivada não recebe chamada.')
    if data > hoje:
        raise DataInvalida('Não é possível lançar chamada para uma data futura.')
    if not (oficina.data_inicio <= data <= oficina.data_fim):
        raise DataInvalida(
            f'A data precisa estar no período da oficina '
            f'({oficina.data_inicio:%d/%m/%Y} a {oficina.data_fim:%d/%m/%Y}).'
        )
    if data.weekday() not in oficina.dias_semana:
        return f'Atenção: {data:%d/%m/%Y} não é um dia da oficina ({oficina.dias_semana_display}). Lançando como reposição.'
    return None


def matriculas_ativas_na_data(oficina, data):
    """Inscritas até a data e ainda cursando (ou encerradas depois dela)."""
    return (
        Matricula.objects.filter(oficina=oficina, data_inscricao__lte=data)
        .filter(
            Q(status=Matricula.Status.CURSANDO)
            | Q(data_conclusao__gte=data)
            | Q(data_desistencia__gte=data)
        )
        .select_related('aluno')
        .order_by('aluno__nome')
    )


def resumo_por_matricula(oficina):
    """Contagem P/F/J e % de frequência ((P + J) / aulas) por matrícula da oficina."""
    linhas = (
        Matricula.objects.filter(oficina=oficina, chamadas__isnull=False)
        .select_related('aluno')
        .annotate(
            presentes=Count('chamadas', filter=Q(chamadas__status_presenca=Chamada.Presenca.PRESENTE)),
            faltas=Count('chamadas', filter=Q(chamadas__status_presenca=Chamada.Presenca.FALTA)),
            justificadas=Count('chamadas', filter=Q(chamadas__status_presenca=Chamada.Presenca.JUSTIFICADA)),
            total=Count('chamadas'),
        )
        .order_by('aluno__nome')
    )
    resultado = []
    for m in linhas:
        percentual = round(100 * (m.presentes + m.justificadas) / m.total) if m.total else None
        resultado.append({'matricula': m, 'percentual': percentual})
    return resultado
