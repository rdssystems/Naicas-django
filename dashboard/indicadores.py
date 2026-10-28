"""
Indicadores do dashboard. Toda função recebe o RECORTE (querysets de oficinas e
alunos já filtrados pelo escopo), então serve tanto para o painel do usuário
(rede, unidade em foco ou unidade do Coordenador) quanto para cada linha da
tabela por unidade. O escopo vem sempre de core.acesso / visiveis_para.
"""

from collections import Counter
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from alunos import etapas
from alunos.models import Aluno
from core import acesso
from escolas.models import EscolaNaica
from frequencia.models import Chamada, RegistroAula
from matriculas.models import Matricula
from oficinas.models import Designacao, Oficina

ATIVAS = (Oficina.Status.ABERTA, Oficina.Status.EM_ANDAMENTO)
META_FREQUENCIA = 75  # % — abaixo disso o aluno entra em "risco de evasão"
MIN_AULAS_RISCO = 3  # com menos aulas lançadas o % ainda não diz nada
JANELA_DIAS = 30
SEMANAS_GRAFICO = 8

PRESENTE_OU_JUSTIFICADA = Q(status_presenca__in=[Chamada.Presenca.PRESENTE, Chamada.Presenca.JUSTIFICADA])


def recorte_do_usuario(user):
    return {
        'oficinas': acesso.filtrar_por_escola(user, Oficina.objects.all()),
        'alunos': Aluno.objects.visiveis_para(user),
    }


def recorte_da_unidade(escola):
    return {
        'oficinas': Oficina.objects.filter(escola=escola),
        'alunos': Aluno.objects.da_unidade(escola),
    }


def _pct(parte, total):
    return round(100 * parte / total) if total else None


# ---------- Alunos ----------

def alunos(recorte):
    qs = recorte['alunos'].select_related('endereco', 'ficha_saude').prefetch_related(*etapas.prefetches())
    pendencias = Counter()
    incompletos = 0
    total = 0
    for aluno in qs:
        total += 1
        faltando = etapas.etapas_pendentes(aluno)
        if faltando:
            incompletos += 1
            pendencias.update(faltando)
    fila = recorte['alunos'].exclude(matriculas__status=Matricula.Status.CURSANDO).count()
    return {
        'total': total,
        'incompletos': incompletos,
        'pendencias': pendencias.most_common(),
        'fila_espera': fila,
    }


# ---------- Matrículas e vagas ----------

def ocupacao(recorte):
    ativas = list(
        recorte['oficinas'].filter(status__in=ATIVAS).select_related('escola')
        .annotate(ocupadas=Count('matriculas', filter=Q(matriculas__status=Matricula.Status.CURSANDO)))
    )
    vagas = sum(o.vagas for o in ativas)
    ocupadas = sum(o.ocupadas for o in ativas)
    for o in ativas:
        o.percentual = _pct(o.ocupadas, o.vagas) or 0
    return {
        'cursando': Matricula.objects.filter(
            oficina__in=recorte['oficinas'], status=Matricula.Status.CURSANDO
        ).count(),
        'vagas': vagas,
        'ocupadas': ocupadas,
        'percentual': _pct(ocupadas, vagas),
        'lotadas': [o for o in ativas if o.ocupadas >= o.vagas],
        'oficinas': sorted(ativas, key=lambda o: (-o.percentual, o.nome)),
    }


# ---------- Frequência ----------

def frequencia(recorte, hoje):
    chamadas = Chamada.objects.filter(registro_aula__oficina__in=recorte['oficinas'])
    janela = chamadas.filter(registro_aula__data_aula__gte=hoje - timedelta(days=JANELA_DIAS))
    totais = janela.aggregate(total=Count('id'), ok=Count('id', filter=PRESENTE_OU_JUSTIFICADA))

    # Semanas (segunda a domingo), da mais antiga para a atual.
    inicio_semana_atual = hoje - timedelta(days=hoje.weekday())
    semanas = []
    for i in range(SEMANAS_GRAFICO - 1, -1, -1):
        inicio = inicio_semana_atual - timedelta(weeks=i)
        da_semana = chamadas.filter(registro_aula__data_aula__range=(inicio, inicio + timedelta(days=6)))
        conta = da_semana.aggregate(total=Count('id'), ok=Count('id', filter=PRESENTE_OU_JUSTIFICADA))
        semanas.append({
            'inicio': inicio,
            'percentual': _pct(conta['ok'], conta['total']),
            'chamadas': conta['total'],
        })

    risco = []
    for m in (
        Matricula.objects.filter(oficina__in=recorte['oficinas'], status=Matricula.Status.CURSANDO)
        .select_related('aluno', 'oficina')
        .annotate(
            aulas=Count('chamadas'),
            ok=Count('chamadas', filter=Q(chamadas__status_presenca__in=['P', 'J'])),
        )
        .filter(aulas__gte=MIN_AULAS_RISCO)
    ):
        m.percentual = _pct(m.ok, m.aulas)
        if m.percentual < META_FREQUENCIA:
            risco.append(m)
    risco.sort(key=lambda m: (m.percentual, m.aluno.nome))

    return {
        'percentual': _pct(totais['ok'], totais['total']),
        'chamadas': totais['total'],
        'semanas': semanas,
        'risco': risco,
    }


# ---------- Operação de hoje ----------

def oficinas_de_hoje(recorte, hoje):
    return list(
        recorte['oficinas'].filter(
            status__in=ATIVAS, dias_semana__contains=[hoje.weekday()],
            data_inicio__lte=hoje, data_fim__gte=hoje,
        ).select_related('escola').order_by('horario', 'nome')
    )


def operacao_de_hoje(recorte, hoje):
    de_hoje = oficinas_de_hoje(recorte, hoje)
    com_chamada = set(
        RegistroAula.objects.filter(oficina__in=de_hoje, data_aula=hoje).values_list('oficina_id', flat=True)
    )
    cobertas = set(
        Designacao.objects.filter(oficina__in=de_hoje, monitor__is_active=True)
        .filter(Q(dias_semana=[]) | Q(dias_semana__contains=[hoje.weekday()]))
        .values_list('oficina_id', flat=True)
    )
    return {
        'oficinas': de_hoje,
        'chamada_pendente': [o for o in de_hoje if o.pk not in com_chamada],
        'sem_monitor': [o for o in de_hoje if o.pk not in cobertas],
    }


# ---------- Comparação entre unidades (visão geral do Diretor) ----------

def por_unidade(hoje):
    linhas = []
    for escola in EscolaNaica.objects.order_by('nome'):
        recorte = recorte_da_unidade(escola)
        ocup = ocupacao(recorte)
        freq = Chamada.objects.filter(
            registro_aula__oficina__in=recorte['oficinas'],
            registro_aula__data_aula__gte=hoje - timedelta(days=JANELA_DIAS),
        ).aggregate(total=Count('id'), ok=Count('id', filter=PRESENTE_OU_JUSTIFICADA))
        hoje_op = operacao_de_hoje(recorte, hoje)
        linhas.append({
            'escola': escola,
            'alunos': recorte['alunos'].count(),
            'cursando': ocup['cursando'],
            'ocupacao': ocup['percentual'],
            'vagas': ocup['vagas'],
            'frequencia': _pct(freq['ok'], freq['total']),
            'pendentes_hoje': len(hoje_op['chamada_pendente']),
            'sem_monitor_hoje': len(hoje_op['sem_monitor']),
        })
    return linhas


def painel(user):
    hoje = timezone.localdate()
    recorte = recorte_do_usuario(user)
    dados = {
        'hoje': hoje,
        'alunos': alunos(recorte),
        'ocupacao': ocupacao(recorte),
        'frequencia': frequencia(recorte, hoje),
        'operacao': operacao_de_hoje(recorte, hoje),
        'meta': META_FREQUENCIA,
    }
    if acesso.is_diretor(user) and not acesso.escola_em_foco(user):
        dados['unidades'] = por_unidade(hoje)
    return dados
