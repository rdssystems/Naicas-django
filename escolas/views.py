from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import DiretorRequiredMixin

from .foco import CHAVE_SESSAO
from .forms import EscolaNaicaForm
from .models import EscolaNaica


class EscolaListView(DiretorRequiredMixin, ListView):
    model = EscolaNaica
    template_name = 'escolas/escola_list.html'
    context_object_name = 'escolas'
    queryset = EscolaNaica.objects.select_related('coordenador_user')


class EscolaFormMixin:
    model = EscolaNaica
    form_class = EscolaNaicaForm
    template_name = 'escolas/escola_form.html'
    success_url = reverse_lazy('escolas:lista')


class EscolaCreateView(DiretorRequiredMixin, EscolaFormMixin, CreateView):
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Unidade "{self.object.nome}" cadastrada.')
        return response


class EscolaUpdateView(DiretorRequiredMixin, EscolaFormMixin, UpdateView):
    context_object_name = 'escola'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Unidade "{self.object.nome}" atualizada.')
        return response


class SelecionarFocoView(DiretorRequiredMixin, View):
    """Diretor entra numa unidade (escola=<id>) ou volta à visão geral (escola vazio)."""

    http_method_names = ['post']

    def post(self, request):
        escola_id = request.POST.get('escola', '')
        if escola_id:
            if not escola_id.isdigit():
                raise Http404
            escola = get_object_or_404(EscolaNaica, pk=escola_id)
            request.session[CHAVE_SESSAO] = escola.pk
            messages.info(request, f'Você entrou na unidade {escola.nome}.')
        else:
            request.session.pop(CHAVE_SESSAO, None)
            messages.info(request, 'Você está na visão geral da rede.')
        destino = request.POST.get('next')
        if destino and url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
            return redirect(destino)
        return redirect('core:home')
