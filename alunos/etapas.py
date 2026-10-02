"""
Registro das etapas do cadastro do aluno.

As etapas 1-4 são do próprio app alunos. As etapas 5 (anexos) e 6 (matrícula)
são registradas pelos apps delas no AppConfig.ready(), para que alunos não
precise importar esses apps (dependência numa só direção: eles -> alunos).

Este módulo não importa models: as funções `concluida` recebem o aluno.
"""

from dataclasses import dataclass
from typing import Callable

# Nome exibido enquanto o app da etapa não estiver instalado/registrado.
NOMES_PADRAO = {
    1: 'Dados do aluno',
    2: 'Responsável',
    3: 'Família e emergência',
    4: 'Saúde',
    5: 'Anexos',
    6: 'Matrícula',
}


@dataclass(frozen=True)
class Etapa:
    numero: int
    nome: str
    url_name: str
    concluida: Callable  # (aluno) -> bool
    conta_para_completo: bool = True
    # Relações que `concluida` lê; a listagem de alunos faz prefetch delas
    # para não gerar uma query por aluno.
    prefetch: tuple = ()


_registro = {}


def registrar(etapa):
    _registro[etapa.numero] = etapa


def etapas_do_aluno(aluno):
    """Lista (número, nome, url_name, concluída?, disponível?) para a navegação."""
    linhas = []
    for numero in sorted(NOMES_PADRAO):
        etapa = _registro.get(numero)
        if etapa is None:
            linhas.append((numero, NOMES_PADRAO[numero], None, False, False))
        else:
            linhas.append((numero, etapa.nome, etapa.url_name, etapa.concluida(aluno), True))
    return linhas


def prefetches():
    return sorted({nome for etapa in _registro.values() for nome in etapa.prefetch})


def cadastro_completo(aluno):
    return all(e.concluida(aluno) for e in _registro.values() if e.conta_para_completo)


def registrar_etapas_do_cadastro():
    """Etapas 1-4 (chamado no AlunosConfig.ready)."""
    registrar(Etapa(1, 'Dados do aluno', 'alunos:etapa_dados', lambda a: hasattr(a, 'endereco')))
    registrar(Etapa(
        2, 'Responsável', 'alunos:etapa_responsaveis', lambda a: bool(a.responsaveis_vinculos.all()),
        prefetch=('responsaveis_vinculos',),
    ))
    registrar(Etapa(
        3, 'Família e emergência', 'alunos:etapa_familia', lambda a: len(a.contatos_emergencia.all()) >= 2,
        prefetch=('contatos_emergencia',),
    ))
    registrar(Etapa(4, 'Saúde', 'alunos:etapa_saude', lambda a: hasattr(a, 'ficha_saude')))
