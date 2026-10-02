"""
Regras de acesso do Naicas: fonte única para "quem é este usuário e o que ele enxerga".

Fica no core (e não em usuarios) para que middleware, mixins e todos os apps
importem daqui sem o core depender de nenhum app de domínio. O Profile é lido
pelo atributo reverso `user.profile`, sem importar usuarios.models.

ATENÇÃO: `escola = None` NÃO significa Diretor. Monitores também não têm
escola (são globais). Acesso de rede é só nivel DIRETOR ou superuser.
"""

from django.db import models


class NivelAcesso(models.TextChoices):
    DIRETOR = 'DIRETOR', 'Diretor'
    COORDENADOR = 'COORDENADOR', 'Coordenador'
    MONITOR = 'MONITOR', 'Monitor'


def get_profile(user):
    if not user or not user.is_authenticated:
        return None
    # RelatedObjectDoesNotExist herda de AttributeError, então o default cobre
    # usuário sem Profile.
    return getattr(user, 'profile', None)


def nivel_do_usuario(user):
    """Nível efetivo. Superuser sem Profile é tratado como Diretor."""
    profile = get_profile(user)
    if profile is not None:
        return profile.nivel_acesso
    if user and user.is_authenticated and user.is_superuser:
        return NivelAcesso.DIRETOR
    return None


def escola_do_usuario(user):
    """
    Unidade fixa do usuário: só o Coordenador tem.
    Regra de ouro: se o Profile tem escola, ela vence o nível.
    """
    profile = get_profile(user)
    return profile.escola if profile is not None else None


def is_diretor(user):
    return nivel_do_usuario(user) == NivelAcesso.DIRETOR and escola_do_usuario(user) is None


def is_coordenador(user):
    return nivel_do_usuario(user) == NivelAcesso.COORDENADOR and escola_do_usuario(user) is not None


def is_monitor(user):
    return nivel_do_usuario(user) == NivelAcesso.MONITOR and escola_do_usuario(user) is None


def tem_acesso_ao_sistema(user):
    return is_diretor(user) or is_coordenador(user) or is_monitor(user)


def pode_gerenciar_escola(user, escola_id):
    """Diretor gerencia qualquer unidade; Coordenador só a própria."""
    if is_diretor(user):
        return True
    if is_coordenador(user):
        return escola_do_usuario(user).pk == escola_id
    return False


def filtrar_por_escola(user, queryset, campo='escola'):
    """
    Restringe um queryset à unidade do usuário. Diretor vê tudo, Coordenador
    só a própria unidade, qualquer outro caso (Monitor incluso) não vê nada:
    o escopo do Monitor é por oficina, não por unidade.
    """
    if is_diretor(user):
        return queryset
    if is_coordenador(user):
        return queryset.filter(**{campo: escola_do_usuario(user)})
    return queryset.none()


def filtrar_oficinas_visiveis(user, queryset):
    """
    Oficinas que o usuário pode ver: Diretor todas, Coordenador as da própria
    unidade, Monitor só as em que está designado (de qualquer unidade).
    """
    if is_monitor(user):
        return queryset.filter(monitores=user)
    return filtrar_por_escola(user, queryset)


def pode_acessar_oficina(user, oficina):
    """
    Lançar chamada / ver matriculados de uma oficina: Diretor, Coordenador da
    unidade da oficina, ou Monitor designado nela (de qualquer unidade).
    """
    if is_diretor(user):
        return True
    if is_coordenador(user):
        return escola_do_usuario(user).pk == oficina.escola_id
    if is_monitor(user):
        return oficina.monitores.filter(pk=user.pk).exists()
    return False
