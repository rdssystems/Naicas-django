"""
Choque de horário entre oficinas. Usado pela matrícula (aluno em duas
oficinas) e pela escala (monitor em duas oficinas).
"""

from types import SimpleNamespace


def janela(oficina, dias=None):
    """Janela de tempo de uma oficina, opcionalmente só em alguns dos dias dela."""
    return SimpleNamespace(
        dias_semana=list(dias) if dias else list(oficina.dias_semana),
        horario=oficina.horario,
        horario_fim=oficina.horario_fim,
        data_inicio=oficina.data_inicio,
        data_fim=oficina.data_fim,
    )


def horarios_se_chocam(a, b):
    """Dia da semana em comum + horários sobrepostos + períodos que se cruzam."""
    return (
        bool(set(a.dias_semana) & set(b.dias_semana))
        and a.horario < b.horario_fim and b.horario < a.horario_fim
        and a.data_inicio <= b.data_fim and b.data_inicio <= a.data_fim
    )
