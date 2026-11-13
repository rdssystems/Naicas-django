"""Comparação de horários semanais, sem período de início ou término."""


def horarios_se_chocam(a, b):
    return (
        bool(set(a.dias_semana) & set(b.dias_semana))
        and a.horario < b.horario_fim and b.horario < a.horario_fim
    )
