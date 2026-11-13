from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views import View

from core import acesso
from core.mixins import PerfilRequiredMixin
from escolas.models import EscolaNaica

from . import grafico, indicadores
from .filtros import FiltrosAlunosForm, com_idade


class DashboardView(PerfilRequiredMixin, View):
    """Diretor (rede inteira ou unidade em foco) e Coordenador (só a unidade dele)."""

    template_name = 'dashboard/painel.html'

    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)

    def get(self, request):
        hoje = timezone.localdate()
        filtros = FiltrosAlunosForm(request.GET, user=request.user)
        validos = filtros.is_valid()
        dados = {
            'hoje': hoje, 'filtros': filtros, 'filtros_validos': validos,
            'unidade_painel': acesso.escola_ativa(request.user),
            'total_unidades': EscolaNaica.objects.count(),
        }
        if validos:
            dados.update(indicadores.painel(request.user, filtros, hoje))
            dados['unidade_painel'] = filtros.cleaned_data.get('escola') or dados['unidade_painel']
            parametros_pendentes = {'classificacao': 'pendente'}
            if dados['unidade_painel']:
                parametros_pendentes['escola'] = dados['unidade_painel'].pk
            dados['url_alunos_pendentes'] = f"{reverse('alunos:lista')}?{urlencode(parametros_pendentes)}"
            dados['grafico'] = grafico.frequencia_semanal(
                dados['frequencia']['semanas'], dados['limiar_frequencia_baixa'],
            )
            dados['filtros_ativos'] = filtros.ativos
            if filtros.ativos:
                alunos = com_idade(dados['alunos_filtrados'], hoje).select_related('escola').order_by('nome', 'pk')
                dados['alunos_encontrados'] = Paginator(alunos, 25).get_page(request.GET.get('page'))
            params = request.GET.copy()
            params.pop('page', None)
            dados['filtros_querystring'] = params.urlencode()
            # Ao entrar numa unidade pela tabela, mantém os critérios de alunos.
            params.pop('escola', None)
            dados['filtros_alunos_querystring'] = params.urlencode()
        return render(request, self.template_name, dados)
