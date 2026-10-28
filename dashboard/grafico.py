"""
Geometria do gráfico de frequência semanal (SVG desenhado no template).
Semana sem chamada lançada não vira 0%: a linha é interrompida ali.
"""

LARGURA, ALTURA = 640, 220
ESQ, DIR, TOPO, BASE = 40, 16, 12, 30  # margens internas (rótulos dos eixos)


def frequencia_semanal(semanas, meta):
    area_l = LARGURA - ESQ - DIR
    area_a = ALTURA - TOPO - BASE
    passo = area_l / max(len(semanas) - 1, 1)

    def y(percentual):
        return round(TOPO + (100 - percentual) / 100 * area_a, 2)

    pontos, segmentos, atual = [], [], []
    for i, s in enumerate(semanas):
        x = round(ESQ + i * passo, 2)
        rotulo = s['inicio'].strftime('%d/%m')
        if s['percentual'] is None:
            if atual:
                segmentos.append(atual)
            atual = []
            pontos.append({'x': x, 'y': None, 'rotulo': rotulo, 'semana': s})
            continue
        ponto = {'x': x, 'y': y(s['percentual']), 'rotulo': rotulo, 'semana': s}
        pontos.append(ponto)
        atual.append(ponto)
    if atual:
        segmentos.append(atual)

    return {
        'largura': LARGURA,
        'altura': ALTURA,
        'esq': ESQ,
        'dir': LARGURA - DIR,
        'base_y': ALTURA - BASE,
        'linhas_grade': [{'valor': v, 'y': y(v)} for v in (0, 25, 50, 100)],
        'meta': {'valor': meta, 'y': y(meta)},
        'segmentos': [' '.join(f'{p["x"]},{p["y"]}' for p in seg) for seg in segmentos],
        'pontos': pontos,
        'meia_coluna': round(passo / 2, 2),
        'tem_dados': any(p['y'] is not None for p in pontos),
    }
