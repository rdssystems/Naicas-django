from django.shortcuts import render
from django.views.generic import TemplateView

from .mixins import PerfilRequiredMixin


class HomeView(PerfilRequiredMixin, TemplateView):
    """
    Painel inicial: só atalhos por papel (via context processor `papel`).
    Não consulta models de outros apps, para o core não depender deles.
    """

    template_name = 'core/home.html'


def erro_403(request, exception=None):
    return render(request, 'core/403.html', status=403)
