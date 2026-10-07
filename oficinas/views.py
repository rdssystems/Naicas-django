from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core import acesso
from core.mixins import CoordenadorUnidadeRequiredMixin, MonitorRequiredMixin, PerfilRequiredMixin
from escolas.models import EscolaNaica

from .forms import OficinaForm, TipoOficinaForm
from .models import Oficina, TipoOficina


class FormComUsuarioMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


# --- Tipos de oficina (Diretor e Coordenador) ---

class TipoOficinaListView(CoordenadorUnidadeRequiredMixin, ListView):
    model = TipoOficina
    template_name = 'oficinas/tipo_list.html'
    context_object_name = 'tipos'

    def get_queryset(self):
        return super().get_queryset().select_related('escola').annotate(
            total_oficinas=Count('oficinas')
        )


class TipoOficinaCreateView(CoordenadorUnidadeRequiredMixin, FormComUsuarioMixin, CreateView):
    model = TipoOficina
    form_class = TipoOficinaForm
    template_name = 'oficinas/tipo_form.html'
    success_url = reverse_lazy('oficinas:tipos')

    def form_valid(self, form):
        messages.success(self.request, f'Tipo "{form.instance.nome}" cadastrado.')
        return super().form_valid(form)


class TipoOficinaUpdateView(CoordenadorUnidadeRequiredMixin, FormComUsuarioMixin, UpdateView):
    model = TipoOficina
    form_class = TipoOficinaForm
    template_name = 'oficinas/tipo_form.html'
    success_url = reverse_lazy('oficinas:tipos')
    context_object_name = 'tipo'

    def form_valid(self, form):
        messages.success(self.request, f'Tipo "{form.instance.nome}" atualizado.')
        return super().form_valid(form)


class TipoOficinaDeleteView(CoordenadorUnidadeRequiredMixin, View):
    http_method_names = ['post']

    def get_queryset(self):
        return acesso.filtrar_por_escola(self.request.user, TipoOficina.objects.all())

    def post(self, request, pk):
        tipo = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            tipo.delete()
            messages.success(request, f'Tipo "{tipo.nome}" excluído.')
        except ProtectedError:
            messages.error(
                request, f'O tipo "{tipo.nome}" está em uso por oficinas e não pode ser excluído.'
            )
        return redirect('oficinas:tipos')


# --- Oficinas ---

class OficinaListView(PerfilRequiredMixin, ListView):
    """Todos os papéis; cada um só vê as oficinas do seu escopo."""

    template_name = 'oficinas/oficina_list.html'
    context_object_name = 'oficinas'
    paginate_by = 25

    def get_queryset(self):
        qs = acesso.filtrar_oficinas_visiveis(
            self.request.user,
            Oficina.objects.select_related('escola', 'tipo_oficina').prefetch_related('monitores'),
        )
        params = self.request.GET
        status = params.get('status', '')
        if status == 'todas':
            pass
        elif status in Oficina.Status.values:
            qs = qs.filter(status=status)
        else:
            qs = qs.exclude(status=Oficina.Status.ARQUIVADO)
        if busca := params.get('q', '').strip():
            qs = qs.filter(Q(nome__icontains=busca) | Q(tipo_oficina__nome__icontains=busca))
        if (escola := params.get('escola')) and acesso.is_diretor(self.request.user):
            qs = qs.filter(escola_id=escola)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Oficina.Status.choices
        # Filtro de unidade só na visão geral do Diretor (dentro de uma unidade é redundante).
        if acesso.is_diretor(self.request.user) and not acesso.escola_em_foco(self.request.user):
            context['escolas'] = EscolaNaica.objects.all()
        filtros = self.request.GET.copy()
        filtros.pop('page', None)
        context['filtros_querystring'] = filtros.urlencode()
        return context


class OficinaDetailView(MonitorRequiredMixin, DetailView):
    """Monitor só entra se estiver designado (checado no MonitorRequiredMixin)."""

    template_name = 'oficinas/oficina_detail.html'
    context_object_name = 'oficina'

    def get_oficina(self):
        return get_object_or_404(
            Oficina.objects.select_related('escola', 'tipo_oficina'), pk=self.kwargs['pk']
        )

    def get_object(self, queryset=None):
        return self.oficina

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['pode_editar'] = acesso.pode_gerenciar_escola(user, self.oficina.escola_id)
        context['monitores'] = self.oficina.monitores.order_by('first_name', 'username')
        return context


class OficinaCreateView(CoordenadorUnidadeRequiredMixin, FormComUsuarioMixin, CreateView):
    model = Oficina
    form_class = OficinaForm
    template_name = 'oficinas/oficina_form.html'

    def form_valid(self, form):
        messages.success(self.request, f'Oficina "{form.instance.nome}" cadastrada.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('oficinas:detalhe', args=[self.object.pk])


class OficinaUpdateView(CoordenadorUnidadeRequiredMixin, FormComUsuarioMixin, UpdateView):
    model = Oficina
    form_class = OficinaForm
    template_name = 'oficinas/oficina_form.html'
    context_object_name = 'oficina'

    def form_valid(self, form):
        messages.success(self.request, f'Oficina "{form.instance.nome}" atualizada.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('oficinas:detalhe', args=[self.object.pk])
