from . import acesso


def papel(request):
    """Flags de papel para montar menus. A permissão real é checada na view."""
    user = getattr(request, 'user', None)
    return {
        'is_diretor': acesso.is_diretor(user),
        'is_coordenador': acesso.is_coordenador(user),
        'is_monitor': acesso.is_monitor(user),
        'active_escola': getattr(request, 'active_escola', None),
    }
