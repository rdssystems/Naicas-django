"""
Regras da escala dos monitores. O dado (quem atende qual oficina, em quais
dias) é oficinas.Designacao; este app só monta, valida e exibe a escala.
"""

from django.db import transaction

from core import acesso
from oficinas.horarios import horarios_se_chocam, janela
from oficinas.models import Designacao, Oficina

STATUS_ATIVOS = (Oficina.Status.ABERTA, Oficina.Status.EM_ANDAMENTO)
DIAS = dict(Oficina.DiaSemana.choices)


class EscalaRecusada(Exception):
    """Motivo legível para o usuário."""


def oficinas_ativas():
    return Oficina.objects.filter(status__in=STATUS_ATIVOS).select_related('escola', 'tipo_oficina')


def oficinas_editaveis(user):
    """Oficinas em que o usuário pode montar escala: Diretor (todas ou a unidade em foco), Coordenador (a dele)."""
    return acesso.filtrar_por_escola(user, oficinas_ativas()).order_by('escola__nome', 'horario', 'nome')


def designacoes_ativas(monitor):
    return Designacao.objects.filter(monitor=monitor, oficina__status__in=STATUS_ATIVOS).select_related(
        'oficina', 'oficina__escola'
    )


def _descrever(oficina, dias):
    return f'"{oficina.nome}" ({oficina.escola.nome}, {", ".join(DIAS[d][:3] for d in sorted(dias))} ' \
           f'{oficina.horario:%H:%M}–{oficina.horario_fim:%H:%M})'


def choques(itens):
    """Pares de (oficina, dias) que se chocam. `itens` é uma lista de (oficina, dias efetivos)."""
    pares = []
    for i, (a, dias_a) in enumerate(itens):
        for b, dias_b in itens[i + 1:]:
            if horarios_se_chocam(janela(a, dias_a), janela(b, dias_b)):
                pares.append(((a, dias_a), (b, dias_b)))
    return pares


@transaction.atomic
def salvar_escala(monitor, user, escolhas):
    """
    Substitui a escala do monitor DENTRO do escopo do usuário.
    `escolhas`: {oficina_id: [dias]} das oficinas marcadas. Designações fora do
    escopo (outra unidade, oficinas encerradas) não são tocadas, mas entram na
    checagem de choque.
    """
    if not (acesso.is_monitor(monitor) and monitor.is_active):
        raise EscalaRecusada('Só monitores ativos podem ser escalados.')

    editaveis = {o.pk: o for o in oficinas_editaveis(user)}
    novos = []
    for oficina_id, dias in escolhas.items():
        oficina = editaveis.get(oficina_id)
        if oficina is None:
            raise EscalaRecusada('Você não pode montar escala nessa oficina.')
        dias = sorted(set(dias))
        if not dias:
            raise EscalaRecusada(f'Escolha pelo menos um dia em "{oficina.nome}".')
        if not set(dias) <= set(oficina.dias_semana):
            raise EscalaRecusada(f'"{oficina.nome}" não acontece em todos os dias escolhidos.')
        novos.append((oficina, dias))

    fora = [(d.oficina, d.dias_efetivos) for d in designacoes_ativas(monitor) if d.oficina_id not in editaveis]
    conflitos = [
        par for par in choques(novos + fora)
        if any(item in novos for item in par)
    ]
    if conflitos:
        (a, dias_a), (b, dias_b) = conflitos[0]
        raise EscalaRecusada(
            f'Choque de horário: {_descrever(a, dias_a)} e {_descrever(b, dias_b)}.'
        )

    Designacao.objects.filter(monitor=monitor, oficina_id__in=editaveis).exclude(
        oficina_id__in=escolhas
    ).delete()
    for oficina, dias in novos:
        # Todos os dias da oficina = lista vazia (acompanha a oficina se ela mudar).
        valor = [] if set(dias) == set(oficina.dias_semana) else dias
        Designacao.objects.update_or_create(oficina=oficina, monitor=monitor, defaults={'dias_semana': valor})


def grade_semanal(user):
    """
    Linhas da grade (monitor × dia) no escopo do usuário. Choques são
    calculados com TODAS as designações ativas do monitor (inclusive de outras
    unidades), mas só os itens do escopo aparecem.
    """
    escopo = acesso.filtrar_por_escola(user, oficinas_ativas())
    designacoes = (
        Designacao.objects.filter(oficina__in=escopo, monitor__is_active=True)
        .select_related('oficina', 'oficina__escola', 'monitor')
        .order_by('monitor__first_name', 'monitor__username', 'oficina__horario')
    )
    por_monitor = {}
    for d in designacoes:
        por_monitor.setdefault(d.monitor, []).append(d)

    linhas, dias_usados = [], set(range(5))  # seg-sex sempre; sáb/dom só se houver
    for monitor, lista in por_monitor.items():
        todas = list(designacoes_ativas(monitor))
        em_choque = set()
        for (a, _), (b, _) in choques([(d.oficina, d.dias_efetivos) for d in todas]):
            em_choque.update({a.pk, b.pk})
        dias = {}
        for d in lista:
            for dia in d.dias_efetivos:
                dias.setdefault(dia, []).append({'designacao': d, 'choque': d.oficina_id in em_choque})
                dias_usados.add(dia)
        for itens in dias.values():
            itens.sort(key=lambda i: i['designacao'].oficina.horario)
        linhas.append({'monitor': monitor, 'dias': dias, 'tem_choque': bool(em_choque)})
    colunas = sorted(dias_usados)
    for linha in linhas:
        # Células alinhadas com as colunas (dias) da grade.
        linha['celulas'] = [linha['dias'].get(dia, []) for dia in colunas]
    return linhas, colunas


def semana_do_monitor(monitor):
    """{dia: [designações]} das oficinas ativas do monitor, por horário."""
    semana = {}
    for d in designacoes_ativas(monitor).order_by('oficina__horario'):
        for dia in d.dias_efetivos:
            semana.setdefault(dia, []).append(d)
    return dict(sorted(semana.items()))


# ---------- Agenda (semana padrão: dias em colunas, horas descendo) ----------

def _minutos(hora):
    return hora.hour * 60 + hora.minute


def _distribuir_em_faixas(blocos):
    """
    Blocos que se sobrepõem dividem a largura da coluna (lado a lado).
    Agrupa em "rodadas" de sobreposição e, em cada uma, põe cada bloco na
    primeira faixa livre. Define 'faixa' e 'faixas' em cada bloco.
    """
    blocos.sort(key=lambda b: (b['inicio'], -b['fim']))
    rodada, fim_rodada, fins_das_faixas = [], -1, []

    def fechar(rodada, total):
        for bloco in rodada:
            bloco['faixas'] = total

    for bloco in blocos:
        if rodada and bloco['inicio'] >= fim_rodada:
            fechar(rodada, len(fins_das_faixas))
            rodada, fins_das_faixas = [], []
        faixa = next((i for i, fim in enumerate(fins_das_faixas) if fim <= bloco['inicio']), None)
        if faixa is None:
            faixa = len(fins_das_faixas)
            fins_das_faixas.append(bloco['fim'])
        else:
            fins_das_faixas[faixa] = bloco['fim']
        bloco['faixa'] = faixa
        rodada.append(bloco)
        fim_rodada = max(fim_rodada, bloco['fim'])
    fechar(rodada, len(fins_das_faixas))


def agenda_semanal(user, monitor=None):
    """
    Colunas por dia com os blocos das oficinas (no escopo do usuário), já
    posicionados em % da coluna. Com `monitor`, só onde ele atende.
    """
    escopo = list(acesso.filtrar_por_escola(user, oficinas_ativas()))
    cobertura = {}
    for d in Designacao.objects.filter(oficina__in=escopo, monitor__is_active=True).select_related('monitor', 'oficina'):
        cobertura.setdefault(d.oficina_id, []).append(d)

    por_dia = {}
    for oficina in escopo:
        for dia in oficina.dias_semana:
            monitores = sorted(
                (d.monitor for d in cobertura.get(oficina.pk, []) if dia in d.dias_efetivos),
                key=lambda m: (m.first_name, m.username),
            )
            if monitor is not None and monitor not in monitores:
                continue
            por_dia.setdefault(dia, []).append({
                'oficina': oficina,
                'monitores': monitores,
                'sem_monitor': not monitores,
                'inicio': _minutos(oficina.horario),
                'fim': _minutos(oficina.horario_fim),
            })

    todos = [b for blocos in por_dia.values() for b in blocos]
    hora_inicio = min([b['inicio'] // 60 for b in todos], default=7)
    hora_fim = max([-(-b['fim'] // 60) for b in todos], default=18)
    hora_inicio = min(hora_inicio, 7)  # agenda começa no máximo às 7h
    hora_fim = max(hora_fim, hora_inicio + 4)  # e mostra pelo menos 4 horas
    total = (hora_fim - hora_inicio) * 60

    dias = sorted(set(range(5)) | set(por_dia))  # seg-sex sempre; sáb/dom só se houver
    colunas = []
    for dia in dias:
        blocos = por_dia.get(dia, [])
        _distribuir_em_faixas(blocos)
        for b in blocos:
            b['top'] = round(100 * (b['inicio'] - hora_inicio * 60) / total, 3)
            b['altura'] = round(100 * (b['fim'] - b['inicio']) / total, 3)
            b['largura'] = round(100 / b['faixas'], 3)
            b['esquerda'] = round(b['faixa'] * b['largura'], 3)
        colunas.append({'dia': dia, 'nome': DIAS[dia], 'blocos': blocos})
    return {
        'colunas': colunas,
        'horas': list(range(hora_inicio, hora_fim)),
        'total_horas': hora_fim - hora_inicio,
        'vazia': not todos,
    }
