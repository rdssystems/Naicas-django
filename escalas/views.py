from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, UpdateView

from core import acesso
from core.mixins import CoordenadorUnidadeRequiredMixin, PerfilRequiredMixin
from oficinas.forms import AtividadeCronogramaForm
from oficinas.models import AtividadeCronograma

from . import regras
from .forms import FiltrosCronogramaDiretorForm


class GradeView(PerfilRequiredMixin, View):
    def get(self, request):
        if acesso.is_diretor(request.user):
            return self.cronograma_diretor(request)
        turma = request.GET.get('turma', '')
        turno = request.GET.get('turno', '')
        if turma not in AtividadeCronograma.Turma.values:
            turma = ''
        if turno not in AtividadeCronograma.Turno.values:
            turno = ''
        return render(request, 'escalas/grade.html', {
            'agenda': regras.agenda_semanal(request.user, turma, turno),
            'turma': turma, 'turno': turno, 'turmas': AtividadeCronograma.Turma.choices,
            'turnos': AtividadeCronograma.Turno.choices, 'hoje': timezone.localdate().weekday(),
        })

    def cronograma_diretor(self, request):
        unidade = acesso.escola_ativa(request.user)
        parametros = request.GET.copy() if request.GET else None
        if parametros is not None and unidade:
            parametros['escola'] = str(unidade.pk)
        filtros = FiltrosCronogramaDiretorForm(parametros, user=request.user)
        agenda = None
        if filtros.is_bound and filtros.is_valid():
            unidade = filtros.cleaned_data['escola']
            agenda = regras.agenda_semanal(
                request.user, escola=unidade, turno=filtros.cleaned_data['turno'],
            )
        return render(request, 'escalas/grade.html', {
            'filtros_diretor': filtros, 'unidade_cronograma': unidade,
            'agenda': agenda, 'hoje': timezone.localdate().weekday(),
        })


class AtividadeDetailView(PerfilRequiredMixin, DetailView):
    model = AtividadeCronograma
    context_object_name = 'atividade'
    template_name = 'escalas/atividade_detail.html'

    def get_queryset(self):
        return acesso.filtrar_oficinas_visiveis(
            self.request.user, super().get_queryset().select_related('escola', 'oficina'),
        )


class FormComUsuarioMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class AtividadeCreateView(CoordenadorUnidadeRequiredMixin, FormComUsuarioMixin, CreateView):
    model = AtividadeCronograma
    form_class = AtividadeCronogramaForm
    template_name = 'escalas/atividade_form.html'
    success_url = reverse_lazy('escalas:grade')

    def get_initial(self):
        initial = super().get_initial()
        initial['oficina'] = self.request.GET.get('oficina')
        return initial

    def form_valid(self, form):
        messages.success(self.request, 'Oficina vinculada ao cronograma das turmas.')
        return super().form_valid(form)


class AtividadeUpdateView(CoordenadorUnidadeRequiredMixin, FormComUsuarioMixin, UpdateView):
    model = AtividadeCronograma
    form_class = AtividadeCronogramaForm
    context_object_name = 'atividade'
    template_name = 'escalas/atividade_form.html'

    def get_success_url(self):
        return reverse('escalas:detalhe', args=[self.object.pk])


class AtividadeDeleteView(CoordenadorUnidadeRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        atividade = get_object_or_404(
            acesso.filtrar_por_escola(request.user, AtividadeCronograma.objects.all()), pk=pk,
        )
        try:
            atividade.delete()
        except ProtectedError:
            # O horário deixa de ser operacional, mas continua referenciável no arquivo.
            atividade.ativo = False
            atividade.save(update_fields=['ativo'])
        messages.success(request, 'Horário removido do cronograma. Histórico preservado.')
        return redirect('escalas:grade')


class EscalaMonitorView(CoordenadorUnidadeRequiredMixin, View):
    http_method_names = ['get']

    def get(self, request, pk):
        return redirect('escalas:grade')


class MinhaSemanaView(PerfilRequiredMixin, View):
    def get(self, request):
        return redirect('escalas:grade')
