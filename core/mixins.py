"""
Mixins de permissão. Toda view do sistema (fora login) usa um deles.

O escopo é aplicado no queryset/objeto, nunca só no template.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from . import acesso


class PerfilRequiredMixin(LoginRequiredMixin):
    """Logado e com papel válido (usuário sem Profile não entra)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.tem_permissao(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def tem_permissao(self, user):
        return acesso.tem_acesso_ao_sistema(user)


class DiretorRequiredMixin(PerfilRequiredMixin):
    def tem_permissao(self, user):
        return acesso.is_diretor(user)


class CoordenadorUnidadeRequiredMixin(PerfilRequiredMixin):
    """
    Diretor ou Coordenador. Em views baseadas em model, o queryset é filtrado
    pela unidade do Coordenador (campo `escola_field`), então um objeto de
    outra unidade dá 404 em vez de vazar.
    """

    escola_field = 'escola'

    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)

    def get_queryset(self):
        return acesso.filtrar_por_escola(
            self.request.user, super().get_queryset(), self.escola_field
        )


class MonitorRequiredMixin(PerfilRequiredMixin):
    """
    Views de frequência/lista de matriculados de UMA oficina. A view define
    get_oficina(); passa Diretor, Coordenador da unidade da oficina e Monitor
    designado nela. Nunca usar em cadastro/edição de aluno, oficina ou usuário.
    """

    def get_oficina(self):
        raise NotImplementedError('A view precisa implementar get_oficina().')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and acesso.tem_acesso_ao_sistema(request.user):
            self.oficina = self.get_oficina()
            if not acesso.pode_acessar_oficina(request.user, self.oficina):
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
