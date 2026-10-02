from . import acesso


class ActiveEscolaMiddleware:
    """
    Define a cada request:
      - request.active_escola: unidade fixa do usuário (só Coordenador tem;
        Diretor e Monitor ficam com None — Monitor pega a unidade da oficina).
      - request.nivel_acesso: DIRETOR / COORDENADOR / MONITOR / None.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_escola = acesso.escola_do_usuario(request.user)
        request.nivel_acesso = acesso.nivel_do_usuario(request.user)
        return self.get_response(request)
