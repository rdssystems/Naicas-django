"""Retorno para a página anterior, com alternativa local para acessos diretos."""
from urllib.parse import urlsplit, urlunsplit

from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from . import acesso


def _alternativa(request):
    rota = request.resolver_match
    if rota is None:
        try:
            rota = resolve(request.path_info)
        except Resolver404:
            return reverse('core:home')
    namespace, nome, pk = rota.namespace, rota.url_name, rota.kwargs.get('pk')
    if namespace == 'usuarios' and nome == 'login':
        return None
    if namespace == 'core' and nome == 'home':
        return reverse('dashboard:painel') if acesso.is_diretor(request.user) or acesso.is_coordenador(request.user) else None
    if namespace == 'alunos':
        if pk and nome != 'detalhe':
            return reverse('alunos:detalhe', args=[pk])
        return reverse('alunos:lista') if nome != 'lista' else reverse('core:home')
    if namespace in ('anexos', 'matriculas') and nome == 'aluno' and pk:
        return reverse('alunos:detalhe', args=[pk])
    if namespace == 'escalas' and nome == 'editar' and pk:
        return reverse('escalas:detalhe', args=[pk])
    if namespace == 'oficinas' and pk and nome != 'detalhe':
        return reverse('oficinas:detalhe', args=[pk])
    listas = {'oficinas': 'oficinas:lista', 'escalas': 'escalas:grade',
              'escolas': 'escolas:lista', 'usuarios': 'usuarios:lista', 'anexos': 'anexos:tipos'}
    destino = listas.get(namespace)
    if destino and rota.view_name != destino:
        return reverse(destino)
    return reverse('core:home')


def retorno_da_pagina(request):
    anterior = request.META.get('HTTP_REFERER', '').strip()
    if anterior and url_has_allowed_host_and_scheme(
        anterior, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        partes = urlsplit(anterior)
        destino = urlunsplit(('', '', partes.path, partes.query, partes.fragment))
        ignorar = {reverse('usuarios:login'), reverse('usuarios:logout')}
        if (partes.path.startswith('/') and not partes.path.startswith('//')
                and partes.path not in ignorar and destino != request.get_full_path()):
            return {'voltar_url': destino, 'voltar_historico': True}
    return {'voltar_url': _alternativa(request), 'voltar_historico': False}
