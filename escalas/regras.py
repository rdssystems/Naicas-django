"""Cronograma semanal das turmas, sem períodos fixos ou atribuições de instrutores."""

from core import acesso
from oficinas.models import AtividadeCronograma

DIAS = dict(AtividadeCronograma.DiaSemana.choices)


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


def agenda_semanal(user, turma=None, turno=None, escola=None):
    """
    Colunas por dia com os blocos das oficinas (no escopo do usuário), já
    posicionados em % da coluna, com filtros por unidade, turma e turno.
    """
    escopo = acesso.filtrar_oficinas_visiveis(user, AtividadeCronograma.objects.filter(ativo=True, oficina__arquivada=False).select_related('escola', 'oficina'))
    if escola is not None:
        escopo = escopo.filter(escola=escola)
    if turma:
        escopo = escopo.filter(turmas__contains=[turma])
    if turno:
        escopo = escopo.filter(turno=turno)

    por_dia = {}
    for oficina in escopo:
        for dia in oficina.dias_semana:
            por_dia.setdefault(dia, []).append({
                'oficina': oficina,
                'inicio': _minutos(oficina.horario),
                'fim': _minutos(oficina.horario_fim),
            })

    todos = [b for blocos in por_dia.values() for b in blocos]
    # Reserva espaço para o conteúdo sem estender o cartão além do seu horário.
    menor_duracao = min((b['fim'] - b['inicio'] for b in todos), default=60)
    altura_hora = round(7.5 * max(1, 60 / max(menor_duracao, 1)), 3)
    hora_inicio = min([b['inicio'] // 60 for b in todos], default=7)
    hora_fim = max([-(-b['fim'] // 60) for b in todos], default=18)
    # Um turno filtrado não precisa reservar a manhã inteira em branco.
    hora_inicio = max(0, hora_inicio - 1) if turno else min(hora_inicio, 7)
    hora_fim = max(hora_fim, hora_inicio + 4)  # e mostra pelo menos 4 horas
    total = (hora_fim - hora_inicio) * 60

    dias = sorted(set(range(5)) | set(por_dia))  # seg-sex sempre; sáb/dom só se houver
    colunas = []
    for dia in dias:
        blocos = por_dia.get(dia, [])
        _distribuir_em_faixas(blocos)
        largura_minima = 13 * max((b['faixas'] for b in blocos), default=1)
        for b in blocos:
            b['top'] = round(100 * (b['inicio'] - hora_inicio * 60) / total, 3)
            b['altura'] = round(100 * (b['fim'] - b['inicio']) / total, 3)
            b['largura'] = round(100 / b['faixas'], 3)
            b['esquerda'] = round(b['faixa'] * b['largura'], 3)
        colunas.append({'dia': dia, 'nome': DIAS[dia], 'blocos': blocos, 'largura_minima': largura_minima})
    return {
        'colunas': colunas,
        'horas': list(range(hora_inicio, hora_fim)),
        'total_horas': hora_fim - hora_inicio,
        'altura_hora': altura_hora,
        'vazia': not todos,
    }
