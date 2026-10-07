from django.contrib.staticfiles.storage import staticfiles_storage
from django.shortcuts import redirect, render
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


def favicon(request):
    """/favicon.ico pedido direto pelo navegador (admin, PDFs abertos no navegador etc.)."""
    # 302, não 301: em produção a URL tem hash e muda se o ícone mudar.
    return redirect(staticfiles_storage.url('core/favicon.ico'))
