"""Etapa 5 do cadastro do atendido, registrada em alunos.etapas pelo AnexosConfig.ready()."""


def tipos_obrigatorios_pendentes(aluno):
    """Tipos obrigatórios (ativos) sem nenhum arquivo enviado para o atendido."""
    from .models import TipoDocumento

    enviados = {a.tipo_documento_id for a in aluno.anexos.all()}  # usa o prefetch da listagem
    return [t for t in TipoDocumento.objects.filter(ativo=True, obrigatorio=True) if t.pk not in enviados]


def documentos_obrigatorios_ok(aluno):
    return not tipos_obrigatorios_pendentes(aluno)
