from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from core import acesso
from core.acesso import NivelAcesso
from core.mixins import PerfilRequiredMixin

from . import regras


class GestaoEscalaMixin(PerfilRequiredMixin):
    """Diretor e Coordenador montam escala (cada um no seu escopo)."""

    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)


def monitores_ativos():
    return User.objects.filter(is_active=True, profile__nivel_acesso=NivelAcesso.MONITOR).order_by(
        'first_name', 'username'
    )


class GradeView(GestaoEscalaMixin, View):
    """Escala com duas abas: Agenda (dias × horas, padrão) e Por monitor (monitor × dias)."""

    template_name = 'escalas/grade.html'

    def get(self, request):
        monitores = monitores_ativos()
        vista = 'monitores' if request.GET.get('vista') == 'monitores' else 'agenda'
        contexto = {
            'vista': vista,
            'monitores': monitores,
            'hoje': timezone.localdate().weekday(),
        }
        if vista == 'agenda':
            filtro = request.GET.get('monitor', '')
            monitor = monitores.filter(pk=filtro).first() if filtro.isdigit() else None
            contexto.update({'agenda': regras.agenda_semanal(request.user, monitor), 'monitor_filtro': monitor})
        else:
            linhas, dias = regras.grade_semanal(request.user)
            com_escala = {linha['monitor'].pk for linha in linhas}
            contexto.update({
                'linhas': linhas,
                'dias': [(d, regras.DIAS[d]) for d in dias],
                'sem_escala': [m for m in monitores if m.pk not in com_escala],
            })
        return render(request, self.template_name, contexto)


class EscalaMonitorView(GestaoEscalaMixin, View):
    """Monta a escala de um monitor: oficinas (do escopo do usuário) e dias de cada uma."""

    template_name = 'escalas/monitor.html'

    def get_monitor(self):
        return get_object_or_404(monitores_ativos(), pk=self.kwargs['pk'])

    def render(self, monitor, escolhas=None):
        atuais = {d.oficina_id: d for d in regras.designacoes_ativas(monitor)}
        editaveis = list(regras.oficinas_editaveis(self.request.user))
        ids_editaveis = {o.pk for o in editaveis}
        grupos = {}
        for oficina in editaveis:
            if escolhas is not None:
                marcada, dias = oficina.pk in escolhas, escolhas.get(oficina.pk, oficina.dias_semana)
            elif oficina.pk in atuais:
                marcada, dias = True, atuais[oficina.pk].dias_efetivos
            else:
                marcada, dias = False, oficina.dias_semana
            grupos.setdefault(oficina.escola, []).append({
                'oficina': oficina,
                'marcada': marcada,
                'dias': [(d, regras.DIAS[d][:3], d in dias) for d in sorted(oficina.dias_semana)],
            })
        return render(self.request, self.template_name, {
            'monitor': monitor,
            'grupos': grupos.items(),
            # Compromissos em outras unidades: só consulta, para evitar choque.
            'outras': [d for d in atuais.values() if d.oficina_id not in ids_editaveis],
        })

    def get(self, request, pk):
        return self.render(self.get_monitor())

    def post(self, request, pk):
        monitor = self.get_monitor()
        escolhas = {}
        for chave in request.POST:
            if chave.startswith('atende_') and chave[7:].isdigit():
                oficina_id = int(chave[7:])
                escolhas[oficina_id] = [
                    int(d) for d in request.POST.getlist(f'dias_{oficina_id}') if d.isdigit() and int(d) in regras.DIAS
                ]
        try:
            regras.salvar_escala(monitor, request.user, escolhas)
        except regras.EscalaRecusada as erro:
            messages.error(request, str(erro))
            return self.render(monitor, escolhas)
        nome = monitor.get_full_name() or monitor.username
        messages.success(request, f'Escala de {nome} salva.')
        return redirect('escalas:grade')


class MinhaSemanaView(PerfilRequiredMixin, View):
    """Agenda do Monitor: oficinas por dia, com atalho para a chamada de hoje."""

    template_name = 'escalas/minha_semana.html'

    def tem_permissao(self, user):
        return acesso.is_monitor(user)

    def get(self, request):
        hoje = timezone.localdate()
        semana = regras.semana_do_monitor(request.user)
        return render(request, self.template_name, {
            'semana': [
                {
                    'dia': dia,
                    'nome': regras.DIAS[dia],
                    'hoje': dia == hoje.weekday(),
                    'designacoes': [
                        {
                            'designacao': d,
                            'chamada_hoje': dia == hoje.weekday() and d.oficina.data_inicio <= hoje <= d.oficina.data_fim,
                        }
                        for d in lista
                    ],
                }
                for dia, lista in semana.items()
            ],
            'hoje': hoje,
        })
