"""Indicadores da unidade/rede: frequência geral e cronograma por turma."""
from collections import Counter
from datetime import timedelta

from django.db.models import Count, F, Q
from django.utils import timezone

from alunos import etapas
from alunos.models import Aluno
from core import acesso
from escolas.models import EscolaNaica
from frequencia.models import ChamadaGeral
from oficinas.models import AtividadeCronograma


LIMIAR_FREQUENCIA_BAIXA = 75
MIN_AULAS_RISCO = 3
JANELA_DIAS = 30
SEMANAS_GRAFICO = 8
PRESENTE_OU_JUSTIFICADA = Q(status_presenca__in=['P', 'J'])


def recorte_do_usuario(user):
    return {
        'escolas': acesso.filtrar_por_escola(user, EscolaNaica.objects.all(), campo='pk'),
        'oficinas': acesso.filtrar_por_escola(user, AtividadeCronograma.objects.all()),
        'alunos': Aluno.objects.visiveis_para(user).ativos(),
    }


def recorte_da_unidade(escola):
    return {'escolas': EscolaNaica.objects.filter(pk=escola.pk),
            'oficinas': AtividadeCronograma.objects.filter(escola=escola), 'alunos': Aluno.objects.da_unidade(escola).ativos()}


def _pct(parte, total):
    return round(100 * parte / total) if total else None


def alunos(recorte):
    qs = recorte['alunos'].select_related('endereco', 'ficha_saude').prefetch_related(*etapas.prefetches())
    pendencias = Counter()
    incompletos = total = 0
    for aluno in qs:
        total += 1
        faltando = etapas.etapas_pendentes(aluno)
        if faltando:
            incompletos += 1
            pendencias.update(faltando)
    return {
        'total': total, 'incompletos': incompletos, 'pendencias': pendencias.most_common(),
        'classificacao_pendente': recorte['alunos'].filter(
            Q(turno__isnull=True) | Q(turno='') | Q(turma__isnull=True) | Q(turma=''),
        ).count(),
    }


def cronograma(recorte):
    ativas = recorte['oficinas'].filter(ativo=True, oficina__arquivada=False)
    return {'oficinas': ativas.select_related('escola', 'oficina').order_by('horario', 'oficina__nome'),
            'total': ativas.count(), 'turmas_pendentes': ativas.filter(turmas=[]).count()}


def chamadas_do_recorte(recorte):
    return ChamadaGeral.objects.filter(
        escola__in=recorte['escolas'], aluno__in=recorte['alunos'], status_presenca__in=['P', 'F', 'J'],
    )


def frequencia(recorte, hoje):
    chamadas = chamadas_do_recorte(recorte).filter(data__lte=hoje)
    janela = chamadas.filter(data__gte=hoje - timedelta(days=JANELA_DIAS))
    totais = janela.aggregate(total=Count('id'), ok=Count('id', filter=PRESENTE_OU_JUSTIFICADA))
    inicio_semana_atual = hoje - timedelta(days=hoje.weekday())
    semanas = []
    for i in range(SEMANAS_GRAFICO - 1, -1, -1):
        inicio = inicio_semana_atual - timedelta(weeks=i)
        conta = chamadas.filter(data__range=(inicio, inicio + timedelta(days=6))).aggregate(
            total=Count('id'), ok=Count('id', filter=PRESENTE_OU_JUSTIFICADA))
        semanas.append({'inicio': inicio, 'percentual': _pct(conta['ok'], conta['total']),
                        'chamadas': conta['total'], 'presencas': conta['ok']})
    risco = []
    for aluno in recorte['alunos'].annotate(
        aulas=Count('chamadas_gerais', filter=Q(chamadas_gerais__in=chamadas)),
        ok=Count('chamadas_gerais', filter=Q(chamadas_gerais__in=chamadas, chamadas_gerais__status_presenca__in=['P', 'J'])),
    ).filter(aulas__gte=MIN_AULAS_RISCO):
        aluno.percentual = _pct(aluno.ok, aluno.aulas)
        if aluno.percentual < LIMIAR_FREQUENCIA_BAIXA:
            risco.append(aluno)
    risco.sort(key=lambda aluno: (aluno.percentual, aluno.nome))
    revisoes = ChamadaGeral.objects.filter(
        escola__in=recorte['escolas'], aluno__in=recorte['alunos'], status_presenca='', data__lte=hoje,
    ).order_by('-data', 'escola__nome').values('data', 'escola_id', 'escola__nome').annotate(total=Count('pk'))
    return {'percentual': _pct(totais['ok'], totais['total']), 'chamadas': totais['total'],
            'semanas': semanas, 'risco': risco, 'revisoes': revisoes}


def oficinas_de_hoje(recorte, hoje):
    return list(recorte['oficinas'].filter(
        ativo=True, oficina__arquivada=False, dias_semana__contains=[hoje.weekday()],
    ).select_related('escola', 'oficina').order_by('horario', 'oficina__nome'))


def operacao_de_hoje(recorte, hoje):
    oficinas = oficinas_de_hoje(recorte, hoje)
    atividades_por_escola = {}
    for atividade in oficinas:
        atividades_por_escola.setdefault(atividade.escola_id, []).append(atividade)
    totais = {
        item['escola']: item
        for item in recorte['alunos'].filter(escola__in=recorte['escolas']).order_by().values('escola').annotate(
            total=Count('pk'),
            **{turno: Count('pk', filter=Q(turno=turno)) for turno in Aluno.Turno.values},
        )
    }
    lancadas = {
        item['escola']: item
        for item in chamadas_do_recorte(recorte).filter(
            data=hoje, aluno__escola_id=F('escola_id'),
        ).order_by().values('escola').annotate(
            total=Count('pk'),
            **{turno: Count('pk', filter=Q(aluno__turno=turno)) for turno in Aluno.Turno.values},
        )
    }
    pendentes, chamadas_por_turno, cronogramas = [], {}, []
    for escola in recorte['escolas']:
        if atividades := atividades_por_escola.get(escola.pk):
            cronogramas.append({'escola': escola, 'atividades': atividades})
        total = totais.get(escola.pk, {})
        lancada = lancadas.get(escola.pk, {})
        faltando = total.get('total', 0) - lancada.get('total', 0)
        if faltando > 0:
            pendentes.append({'escola': escola, 'pendentes': faltando})
        turnos = [
            {'turno': turno, 'rotulo': rotulo, 'total': total.get(turno, 0),
             'pendentes': total.get(turno, 0) - lancada.get(turno, 0)}
            for turno, rotulo in Aluno.Turno.choices
        ]
        sem_turno = total.get('total', 0) - sum(item['total'] for item in turnos)
        if sem_turno:
            lancadas_sem_turno = lancada.get('total', 0) - sum(lancada.get(turno, 0) for turno in Aluno.Turno.values)
            turnos.append({'turno': '', 'rotulo': 'Sem turno', 'total': sem_turno,
                           'pendentes': sem_turno - lancadas_sem_turno})
        chamadas_por_turno[escola.pk] = turnos
    return {'oficinas': oficinas, 'cronogramas': cronogramas, 'chamada_pendente': pendentes,
            'chamadas_por_turno': chamadas_por_turno}


def por_unidade(hoje, filtros=None):
    linhas = []
    for escola in EscolaNaica.objects.order_by('nome'):
        recorte = recorte_da_unidade(escola)
        if filtros is not None:
            recorte = filtros.filtrar_recorte(recorte, hoje)
        freq = chamadas_do_recorte(recorte).filter(data__range=(hoje - timedelta(days=JANELA_DIAS), hoje)).aggregate(
            total=Count('id'), ok=Count('id', filter=PRESENTE_OU_JUSTIFICADA))
        operacao = operacao_de_hoje(recorte, hoje)
        linhas.append({'escola': escola, 'alunos': recorte['alunos'].count(),
                       'oficinas': recorte['oficinas'].filter(ativo=True, oficina__arquivada=False).count(),
                       'frequencia': _pct(freq['ok'], freq['total']),
                       'chamadas_por_turno': operacao['chamadas_por_turno'][escola.pk],
                       'pendentes_hoje': sum(item['pendentes'] for item in operacao['chamada_pendente'])})
    return linhas


def painel(user, filtros=None, hoje=None):
    hoje = hoje or timezone.localdate()
    recorte = recorte_do_usuario(user)
    if filtros is not None:
        recorte = filtros.filtrar_recorte(recorte, hoje)
    dados = {'hoje': hoje, 'alunos': alunos(recorte), 'cronograma': cronograma(recorte),
             'frequencia': frequencia(recorte, hoje), 'operacao': operacao_de_hoje(recorte, hoje),
             'limiar_frequencia_baixa': LIMIAR_FREQUENCIA_BAIXA,
             'alunos_filtrados': recorte['alunos']}
    escola_filtrada = filtros.cleaned_data.get('escola') if filtros is not None else None
    if acesso.is_diretor(user) and not acesso.escola_em_foco(user) and not escola_filtrada:
        dados['unidades'] = por_unidade(hoje, filtros)
    return dados
