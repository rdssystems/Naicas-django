"""
Extensões da visibilidade do Coordenador sobre alunos.

Por padrão o Coordenador vê os alunos cadastrados na unidade dele. Outros apps
(ex.: matriculas) acrescentam critérios no AppConfig.ready(), sem que alunos
precise importá-los. Cada critério é uma função (escola) -> Q sobre Aluno.
"""

_criterios = []


def registrar_criterio_coordenador(funcao):
    if funcao not in _criterios:
        _criterios.append(funcao)


def criterios_coordenador(escola):
    return [funcao(escola) for funcao in _criterios]
