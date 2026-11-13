from datetime import date
from itertools import groupby

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views import View

from alunos.models import Aluno
from core import acesso
from core.mixins import PerfilRequiredMixin
from escolas.models import EscolaNaica
from oficinas.models import AtividadeCronograma

from .models import ChamadaGeral


class GestaoFrequenciaMixin(PerfilRequiredMixin):
    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)


class ChamadaNaicaView(GestaoFrequenciaMixin, View):
    """Uma presença por atendido/data na unidade, sem depender de oficinas."""

    template_name = 'frequencia/chamada_naica.html'

    def unidades_visiveis(self):
        return acesso.filtrar_por_escola(self.request.user, EscolaNaica.objects.all(), campo='pk')

    def unidade(self, unidade_id=None):
        ativa = acesso.escola_ativa(self.request.user)
        if ativa:
            return ativa
        unidade_id = unidade_id or self.request.GET.get('escola')
        if unidade_id and not str(unidade_id).isdigit():
            raise Http404
        return get_object_or_404(self.unidades_visiveis(), pk=unidade_id) if unidade_id else None

    @staticmethod
    def ler_data(valor):
        try:
            return date.fromisoformat(valor)
        except (TypeError, ValueError):
            return None

    def linhas(self, escola, data, turno=''):
        existentes = {
            chamada.aluno_id: chamada
            for chamada in ChamadaGeral.objects.filter(escola=escola, data=data)
        }
        # O histórico continua corrigível após mudança de unidade ou status.
        alunos = Aluno.objects.filter(Q(escola=escola, status=Aluno.Status.ATIVO) | Q(pk__in=existentes))
        if turno:
            alunos = alunos.filter(turno=turno)
        # Alunos antigos sem classificação também participam da chamada.
        linhas = [{
            'aluno': aluno, 'chamada': existentes.get(aluno.pk),
            'revisar': aluno.pk in existentes and not existentes[aluno.pk].status_presenca,
        } for aluno in alunos]
        linhas.sort(key=lambda linha: (
            linha['aluno'].turno or 'Z', linha['aluno'].turma or 'Z',
            linha['aluno'].nome.casefold(), linha['aluno'].pk,
        ))
        return [{
            'turno_label': dict(Aluno.Turno.choices).get(turno, 'Turno pendente'),
            'turma_label': dict(Aluno.Turma.choices).get(turma, 'Turma pendente'),
            'alunos': list(itens),
        } for (turno, turma), itens in groupby(linhas, lambda linha: (linha['aluno'].turno, linha['aluno'].turma))]

    def render(self, request, escola, data, erro=None, turno='', grupos=None):
        if turno not in ('', *Aluno.Turno.values):
            turno = ''
        if grupos is None:
            grupos = self.linhas(escola, data, turno) if escola and not erro and data <= timezone.localdate() else []
        return render(request, self.template_name, {
            'escola': escola, 'escolas': self.unidades_visiveis(), 'data': data,
            'turno': turno, 'grupos': grupos, 'presencas': ChamadaGeral.Presenca.choices,
            'erro': erro, 'total_alunos': sum(len(grupo['alunos']) for grupo in grupos),
        })

    def get(self, request):
        escola = self.unidade()
        data = self.ler_data(request.GET['data']) if request.GET.get('data') else timezone.localdate()
        erro = 'Informe uma data válida.' if data is None else None
        data = data or timezone.localdate()
        if data > timezone.localdate():
            erro = 'Não é possível lançar chamada para uma data futura.'
        return self.render(request, escola, data, erro, request.GET.get('turno', ''))

    def post(self, request):
        escola = self.unidade(request.POST.get('escola'))
        data = self.ler_data(request.POST.get('data'))
        turno = request.POST.get('turno', '')
        if turno not in ('', *Aluno.Turno.values):
            return self.render(request, escola, data or timezone.localdate(), 'Informe um turno válido.')
        if data is None:
            return self.render(request, escola, timezone.localdate(), 'Informe uma data válida.', turno)
        if escola is None:
            return self.render(request, escola, data, 'Selecione uma Naica para lançar a chamada.', turno)
        if data > timezone.localdate():
            return self.render(request, escola, data, 'Não é possível lançar chamada para uma data futura.', turno)
        grupos = self.linhas(escola, data, turno)
        respostas = []
        erro = None
        for grupo in grupos:
            for linha in grupo['alunos']:
                aluno = linha['aluno']
                valor = request.POST.get(f'presenca_{aluno.pk}')
                obs = request.POST.get(f'obs_{aluno.pk}', '').strip()[:255]
                if valor not in ChamadaGeral.Presenca.values:
                    erro = f'Marque a presença de {aluno.nome}.'
                linha['chamada'] = {'status_presenca': valor, 'observacoes': obs}
                respostas.append((aluno, valor, obs))
        if erro:
            return self.render(request, escola, data, erro, turno, grupos)
        with transaction.atomic():
            for aluno, presenca, observacoes in respostas:
                chamada, criada = ChamadaGeral.objects.get_or_create(
                    escola=escola, aluno=aluno, data=data,
                    defaults={'status_presenca': presenca, 'observacoes': observacoes, 'lancado_por': request.user},
                )
                if not criada:
                    chamada.status_presenca = presenca
                    chamada.observacoes = observacoes
                    chamada.atualizado_por = request.user
                    chamada.save(update_fields=['status_presenca', 'observacoes', 'atualizado_por', 'atualizado_em'])
        messages.success(request, f'Chamada geral de {data:%d/%m/%Y} salva: {len(respostas)} atendido(s).')
        return redirect(f"{reverse('frequencia:chamada_naica')}?{urlencode({'escola': escola.pk, 'data': data.isoformat(), 'turno': turno})}")


class FrequenciaOficinaLegadaView(GestaoFrequenciaMixin, View):
    """Atalhos antigos levam à chamada geral; não há escrita por oficina."""

    http_method_names = ['get']

    def get(self, request, pk, **kwargs):
        oficina = get_object_or_404(acesso.filtrar_por_escola(request.user, AtividadeCronograma.objects.all()), pk=pk)
        params = {'escola': oficina.escola_id}
        if data := request.GET.get('data'):
            params['data'] = data
        return redirect(f"{reverse('frequencia:chamada_naica')}?{urlencode(params)}")
