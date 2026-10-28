from django.shortcuts import render
from django.views import View

from core import acesso
from core.mixins import PerfilRequiredMixin

from . import grafico, indicadores


class DashboardView(PerfilRequiredMixin, View):
    """Diretor (rede inteira ou unidade em foco) e Coordenador (só a unidade dele)."""

    template_name = 'dashboard/painel.html'

    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)

    def get(self, request):
        dados = indicadores.painel(request.user)
        dados['grafico'] = grafico.frequencia_semanal(dados['frequencia']['semanas'], dados['meta'])
        return render(request, self.template_name, dados)
