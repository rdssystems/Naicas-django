from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import DiretorRequiredMixin

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
