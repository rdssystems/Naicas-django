from . import acesso


class ActiveEscolaMiddleware:
    """
    Define a cada request:
      - request.active_escola: unidade em que o usuário está operando — a fixa
        do Coordenador ou a escolhida pelo Diretor (escolas.middleware roda
        antes e define o foco). Monitor fica com None: a unidade vem da oficina.
      - request.nivel_acesso: DIRETOR / COORDENADOR / MONITOR / None.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_escola = acesso.escola_ativa(request.user)
        request.nivel_acesso = acesso.nivel_do_usuario(request.user)
        return self.get_response(request)
