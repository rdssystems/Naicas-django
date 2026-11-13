from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core import acesso
from core.mixins import DiretorRequiredMixin, PerfilRequiredMixin

from .forms import OficinaForm
from .models import AtividadeCronograma, Oficina


def catalogo_visivel(user):
    qs = Oficina.objects.all()
    if acesso.is_monitor(user):
        qs = qs.filter(atividades__monitores=user).distinct()
    return qs


class OficinaListView(PerfilRequiredMixin, ListView):
    template_name = 'oficinas/oficina_list.html'
    context_object_name = 'oficinas'
    paginate_by = 25

    def get_queryset(self):
        qs = catalogo_visivel(self.request.user)
        status = self.request.GET.get('status', '')
        if status != 'todas':
            qs = qs.filter(arquivada=status == 'arquivadas')
        if busca := self.request.GET.get('q', '').strip():
            qs = qs.filter(nome__icontains=busca)
        atividades = acesso.filtrar_oficinas_visiveis(self.request.user, AtividadeCronograma.objects.all())
        return qs.annotate(total_horarios=Count('atividades', filter=Q(
            atividades__ativo=True, atividades__in=atividades,
        ))).order_by('nome', 'pk')

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop('page', None)
        contexto['filtros_querystring'] = params.urlencode()
        return contexto


class OficinaDetailView(PerfilRequiredMixin, DetailView):
    template_name = 'oficinas/oficina_detail.html'
    context_object_name = 'oficina'

    def get_queryset(self):
        return catalogo_visivel(self.request.user)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['atividades'] = acesso.filtrar_oficinas_visiveis(
            self.request.user,
            AtividadeCronograma.objects.filter(oficina=self.object, ativo=True).select_related('escola', 'oficina'),
        )
        return contexto


class OficinaCreateView(DiretorRequiredMixin, CreateView):
    model = Oficina
    form_class = OficinaForm
    template_name = 'oficinas/oficina_form.html'
    success_url = reverse_lazy('oficinas:lista')

    def form_valid(self, form):
        messages.success(self.request, 'Oficina criada no catálogo da rede.')
        return super().form_valid(form)


class OficinaUpdateView(DiretorRequiredMixin, UpdateView):
    model = Oficina
    form_class = OficinaForm
    template_name = 'oficinas/oficina_form.html'
    context_object_name = 'oficina'

    def get_success_url(self):
        return reverse('oficinas:detalhe', args=[self.object.pk])


class ArquivarOficinaView(DiretorRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        oficina = get_object_or_404(Oficina, pk=pk)
        oficina.arquivada = not oficina.arquivada
        oficina.save(update_fields=['arquivada'])
        messages.success(request, 'Oficina arquivada.' if oficina.arquivada else 'Oficina reativada.')
        return redirect('oficinas:detalhe', pk=pk)


class ExcluirOficinaView(DiretorRequiredMixin, DetailView):
    model = Oficina
    template_name = 'oficinas/oficina_confirm_delete.html'
    context_object_name = 'oficina'

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['total_horarios'] = self.object.atividades.filter(ativo=True).count()
        return contexto

    @transaction.atomic
    def post(self, request, pk):
        oficina = get_object_or_404(Oficina.objects.select_for_update(), pk=pk)
        # SET_NULL retira os vínculos do cronograma e mantém o arquivo histórico.
        oficina.delete()
        messages.success(request, 'Oficina excluída do catálogo e do cronograma. Histórico preservado.')
        return redirect('oficinas:lista')


class CatalogoAntigoView(PerfilRequiredMixin, View):
    http_method_names = ['get']

    def get(self, request, **kwargs):
        return redirect('oficinas:lista')
