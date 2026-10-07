"""
"Entrar" numa unidade: o Diretor escolhe uma Escola Naica na barra do topo e
passa a ver só os dados dela (ou volta à visão geral). A escolha fica na
sessão; o middleware põe a unidade em `request.user.escola_em_foco`, que é o
que core.acesso lê para filtrar. O foco só RESTRINGE o que o Diretor vê:
para qualquer outro papel ele é ignorado.
"""

from core import acesso

from .models import EscolaNaica

CHAVE_SESSAO = 'escola_em_foco_id'


class EscolaEmFocoMiddleware:
    """Precisa vir depois do AuthenticationMiddleware e antes do core.ActiveEscolaMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        escola_id = request.session.get(CHAVE_SESSAO)
        if escola_id is not None:
            escola = EscolaNaica.objects.filter(pk=escola_id).first() if acesso.is_diretor(user) else None
            if escola is None:
                # Unidade apagada ou usuário que não é (mais) Diretor: volta à visão geral.
                request.session.pop(CHAVE_SESSAO, None)
            else:
                user.escola_em_foco = escola
        return self.get_response(request)


def unidades(request):
    """Context processor: unidades do seletor (só para Diretor). Sempre lidas do banco."""
    user = getattr(request, 'user', None)
    if not acesso.is_diretor(user):
        return {}
    return {'unidades_para_foco': EscolaNaica.objects.only('pk', 'nome')}
