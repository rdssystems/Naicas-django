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


def escola_em_foco(user):
    """
    Unidade em que o Diretor "entrou" (escolhida na barra, guardada na sessão
    pelo app escolas, que põe o atributo `escola_em_foco` no usuário).
    None = visão geral. Só vale para Diretor: o foco não dá poder a ninguém,
    ele apenas RESTRINGE o que o Diretor vê.
    """
    return getattr(user, 'escola_em_foco', None) if is_diretor(user) else None


def escola_ativa(user):
    """
    Unidade em que o usuário está operando agora (nome na barra, filtros):
    a fixa do Coordenador ou a escolhida pelo Diretor. Regra de ouro: a
    escola do Profile vem primeiro e nunca é sobrescrita pelo foco.
    """
    return escola_do_usuario(user) or escola_em_foco(user)


def pode_gerenciar_escola(user, escola_id):
    """Diretor gerencia qualquer unidade; Coordenador só a própria."""
    if is_diretor(user):
        return True
    if is_coordenador(user):
        return escola_do_usuario(user).pk == escola_id
    return False


def filtrar_por_escola(user, queryset, campo='escola'):
    """
    Restringe um queryset à unidade do usuário. Diretor vê tudo (ou só a
    unidade em foco, se entrou numa), Coordenador só a própria unidade,
    qualquer outro caso (Monitor incluso) não vê nada: o escopo do Monitor é
    por oficina, não por unidade.
    """
    if is_diretor(user):
        foco = escola_em_foco(user)
        return queryset.filter(**{campo: foco.pk}) if foco else queryset
    if is_coordenador(user):
        return queryset.filter(**{campo: escola_do_usuario(user).pk})
    return queryset.none()


def filtrar_oficinas_visiveis(user, queryset):
    """
    Atividades do cronograma: Diretor todas, Coordenador as da própria
    unidade, Monitor só as em que está designado (de qualquer unidade).
    """
    if is_monitor(user):
        return queryset.filter(monitores=user)
    return filtrar_por_escola(user, queryset)


# --- Dados de saúde (LGPD) ---
# Ponto ÚNICO de decisão sobre quem vê a ficha de saúde do aluno. A regra do
# Monitor ainda será definida (pós-MVP): por enquanto ele não vê nada. Estas
# funções decidem o PAPEL; a visibilidade do aluno em si (unidade) é checada
# antes, pelo Aluno.objects.visiveis_para.

def pode_ver_saude_completa(user):
    """Prontuário inteiro (assistência, condições, medicação, alergias)."""
    return is_diretor(user) or is_coordenador(user)


def pode_ver_saude_emergencia(user):
    """Mínimo para agir numa emergência: alergias e medicação controlada."""
    return pode_ver_saude_completa(user)


def pode_acessar_oficina(user, oficina):
    """
    Consultar o cronograma de uma oficina: Diretor, Coordenador da
    unidade da oficina, ou Monitor designado nela (de qualquer unidade).
    """
    if is_diretor(user):
        return True
    if is_coordenador(user):
        return escola_do_usuario(user).pk == oficina.escola_id
    if is_monitor(user):
        return oficina.monitores.filter(pk=user.pk).exists()
    return False
