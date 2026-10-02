from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views import View

from core import acesso
from core.mixins import MonitorRequiredMixin
from oficinas.models import Oficina

from . import regras
from .models import Chamada, RegistroAula


class OficinaFrequenciaMixin(MonitorRequiredMixin):
    """Diretor, Coordenador da unidade da oficina e Monitor designado nela."""

    def get_oficina(self):
        return get_object_or_404(Oficina.objects.select_related('escola'), pk=self.kwargs['pk'])


class FrequenciaOficinaView(OficinaFrequenciaMixin, View):
    template_name = 'frequencia/oficina_frequencia.html'

    def get(self, request, pk):
        oficina = self.oficina
        aulas = oficina.aulas.select_related('lancado_por').annotate(
            presentes=Count('chamadas', filter=Q(chamadas__status_presenca=Chamada.Presenca.PRESENTE)),
            faltas=Count('chamadas', filter=Q(chamadas__status_presenca=Chamada.Presenca.FALTA)),
            justificadas=Count('chamadas', filter=Q(chamadas__status_presenca=Chamada.Presenca.JUSTIFICADA)),
        )
        hoje = timezone.localdate()
        return render(request, self.template_name, {
            'oficina': oficina,
            'aulas': aulas,
            'resumo': regras.resumo_por_matricula(oficina),
            'data_sugerida': min(max(hoje, oficina.data_inicio), oficina.data_fim, hoje),
            'hoje': hoje,
            'pode_excluir': acesso.pode_gerenciar_escola(request.user, oficina.escola_id),
        })


class ChamadaView(OficinaFrequenciaMixin, View):
    """Lança ou corrige a chamada de uma data (?data=AAAA-MM-DD)."""

    template_name = 'frequencia/chamada.html'

    def ler_data(self, valor):
        try:
            return date.fromisoformat(valor)
        except (TypeError, ValueError):
            return None

    def voltar(self, mensagem):
        messages.error(self.request, mensagem)
        return redirect('frequencia:oficina', pk=self.oficina.pk)

    def linhas(self, data, registro):
        existentes = {c.matricula_id: c for c in registro.chamadas.select_related('matricula__aluno')} if registro else {}
        matriculas = {m.pk: m for m in regras.matriculas_ativas_na_data(self.oficina, data)}
        # Na correção, quem já tinha chamada continua na lista mesmo se a matrícula mudou depois.
        for chamada in existentes.values():
            matriculas.setdefault(chamada.matricula_id, chamada.matricula)
        return [
            {'matricula': m, 'chamada': existentes.get(m.pk)}
            for m in sorted(matriculas.values(), key=lambda m: m.aluno.nome)
        ]

    def get(self, request, pk):
        data = self.ler_data(request.GET.get('data'))
        if data is None:
            return self.voltar('Informe a data da aula.')
        try:
            aviso = regras.validar_data_aula(self.oficina, data)
        except regras.DataInvalida as erro:
            return self.voltar(str(erro))
        registro = RegistroAula.objects.filter(oficina=self.oficina, data_aula=data).first()
        return render(request, self.template_name, {
            'oficina': self.oficina, 'data': data, 'registro': registro, 'aviso': aviso,
            'linhas': self.linhas(data, registro), 'presencas': Chamada.Presenca.choices,
        })

    def post(self, request, pk):
        data = self.ler_data(request.POST.get('data'))
        if data is None:
            return self.voltar('Informe a data da aula.')
        try:
            regras.validar_data_aula(self.oficina, data)
        except regras.DataInvalida as erro:
            return self.voltar(str(erro))

        registro = RegistroAula.objects.filter(oficina=self.oficina, data_aula=data).first()
        linhas = self.linhas(data, registro)
        validos = set(Chamada.Presenca.values)
        respostas = {}
        for linha in linhas:
            m = linha['matricula']
            valor = request.POST.get(f'presenca_{m.pk}')
            if valor not in validos:
                messages.error(request, f'Marque a presença de {m.aluno.nome}.')
                return redirect(f"{reverse('frequencia:chamada', args=[self.oficina.pk])}?{urlencode({'data': data.isoformat()})}")
            respostas[m.pk] = (valor, request.POST.get(f'obs_{m.pk}', '').strip()[:255])

        with transaction.atomic():
            registro, criado = RegistroAula.objects.get_or_create(
                oficina=self.oficina, data_aula=data, defaults={'lancado_por': request.user},
            )
            registro.observacoes = request.POST.get('observacoes', '').strip()
            registro.atualizado_por = request.user
            registro.save()
            for matricula_id, (presenca, obs) in respostas.items():
                Chamada.objects.update_or_create(
                    registro_aula=registro, matricula_id=matricula_id,
                    defaults={'status_presenca': presenca, 'observacoes': obs},
                )
        faltas = sum(1 for p, _ in respostas.values() if p == Chamada.Presenca.FALTA)
        acao = 'lançada' if criado else 'corrigida'
        messages.success(request, f'Chamada de {data:%d/%m/%Y} {acao}: {len(respostas)} aluno(s), {faltas} falta(s).')
        return redirect('frequencia:oficina', pk=self.oficina.pk)


class ExcluirAulaView(OficinaFrequenciaMixin, View):
    """Só Diretor/Coordenador (aula lançada na data errada). Monitor não exclui."""

    http_method_names = ['post']

    def post(self, request, pk, aula_pk):
        if not acesso.pode_gerenciar_escola(request.user, self.oficina.escola_id):
            raise PermissionDenied
        aula = get_object_or_404(RegistroAula, pk=aula_pk, oficina=self.oficina)
        aula.delete()
        messages.success(request, f'Chamada de {aula.data_aula:%d/%m/%Y} excluída.')
        return redirect('frequencia:oficina', pk=self.oficina.pk)
