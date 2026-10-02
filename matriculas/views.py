from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from alunos.models import Aluno
from alunos.views import CadastroAlunoMixin
from core import acesso
from core.mixins import MonitorRequiredMixin, PerfilRequiredMixin
from core.validators import so_digitos
from oficinas.models import Oficina

from . import regras
from .models import Matricula


def redirecionar(request, padrao):
    """Volta para a tela de origem (campo `next`), se for uma URL interna."""
    destino = request.POST.get('next') or request.GET.get('next')
    if destino and url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
        return redirect(destino)
    return redirect(padrao)


def idade(nascimento, hoje=None):
    hoje = hoje or date.today()
    return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


class MatriculadosOficinaView(MonitorRequiredMixin, View):
    """Lista de matriculados: Diretor, Coordenador da unidade e Monitor designado."""

    template_name = 'matriculas/oficina_matriculados.html'

    def get_oficina(self):
        return get_object_or_404(Oficina.objects.select_related('escola', 'tipo_oficina'), pk=self.kwargs['pk'])

    def get(self, request, pk):
        oficina = self.oficina
        user = request.user
        mostrar_todas = request.GET.get('situacao') == 'todas'
        matriculas = oficina.matriculas.select_related('aluno').order_by('aluno__nome')
        if not mostrar_todas:
            matriculas = matriculas.filter(status=Matricula.Status.CURSANDO)
        if acesso.pode_ver_saude_emergencia(user):
            matriculas = matriculas.select_related('aluno__ficha_saude')
        linhas = [{'matricula': m, 'idade': idade(m.aluno.data_nascimento)} for m in matriculas]
        ocupadas = regras.vagas_ocupadas(oficina)
        return render(request, self.template_name, {
            'oficina': oficina,
            'linhas': linhas,
            'mostrar_todas': mostrar_todas,
            'vagas_ocupadas': ocupadas,
            'vagas_livres': max(oficina.vagas - ocupadas, 0),
            'pode_gerenciar': acesso.pode_gerenciar_escola(user, oficina.escola_id),
            'pode_ver_saude': acesso.pode_ver_saude_emergencia(user),
            'aceita_matricula': oficina.status in regras.STATUS_ABERTOS,
        })


class GestaoOficinaMixin(PerfilRequiredMixin):
    """Diretor ou Coordenador da unidade da oficina."""

    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)

    def get_oficina(self):
        oficina = get_object_or_404(Oficina.objects.select_related('escola'), pk=self.kwargs['pk'])
        if not acesso.pode_gerenciar_escola(self.request.user, oficina.escola_id):
            # Mesmo comportamento do resto do sistema: de outra unidade = não existe.
            raise Http404
        return oficina


class MatricularNaOficinaView(GestaoOficinaMixin, View):
    """
    Busca o aluno (por nome entre os visíveis, ou por CPF exato na rede toda)
    e matricula na oficina. Aluno de outra unidade só é encontrado pelo CPF
    completo, e só mostra nome, nascimento e unidade de cadastro.
    """

    template_name = 'matriculas/matricular_na_oficina.html'

    def get(self, request, pk):
        oficina = self.get_oficina()
        busca = request.GET.get('q', '').strip()
        visiveis = Aluno.objects.visiveis_para(request.user)
        resultados, de_outra_unidade = [], None
        if busca:
            digitos = so_digitos(busca)
            if len(digitos) == 11:
                aluno = Aluno.objects.select_related('escola').filter(cpf=digitos).first()
                if aluno and visiveis.filter(pk=aluno.pk).exists():
                    resultados = [aluno]
                elif aluno:
                    de_outra_unidade = aluno
            else:
                resultados = list(visiveis.filter(Q(nome__icontains=busca) | Q(nome_mae__icontains=busca))
                                  .select_related('escola')[:20])
        cursando = set(
            oficina.matriculas.filter(status=Matricula.Status.CURSANDO).values_list('aluno_id', flat=True)
        )
        return render(request, self.template_name, {
            'oficina': oficina,
            'busca': busca,
            'resultados': [{'aluno': a, 'ja_cursando': a.pk in cursando} for a in resultados],
            'de_outra_unidade': de_outra_unidade,
            'vagas_livres': max(oficina.vagas - regras.vagas_ocupadas(oficina), 0),
        })

    def post(self, request, pk):
        oficina = self.get_oficina()
        # Visível pelo id; de outra unidade, só pelo CPF (quem matricula precisa conhecê-lo).
        if request.POST.get('cpf'):
            aluno = get_object_or_404(Aluno, cpf=so_digitos(request.POST['cpf']))
        else:
            aluno = get_object_or_404(Aluno.objects.visiveis_para(request.user), pk=request.POST.get('aluno'))
        try:
            regras.matricular(aluno, oficina, request.user)
            messages.success(request, f'{aluno.nome} matriculado(a) em "{oficina.nome}".')
            return redirect('matriculas:oficina', pk=oficina.pk)
        except regras.MatriculaRecusada as erro:
            messages.error(request, str(erro))
            return redirect(f"{request.path}?{urlencode({'q': request.POST.get('q', '')})}")


class EtapaMatriculaView(CadastroAlunoMixin, View):
    """Etapa 6 do cadastro: matrículas do aluno + matricular numa oficina."""

    template_name = 'matriculas/aluno_matriculas.html'

    def get(self, request, pk):
        aluno = self.get_aluno()
        matriculas = aluno.matriculas.select_related('oficina', 'escola').order_by('status', '-data_inscricao')
        cursando = {m.oficina_id for m in matriculas if m.status == Matricula.Status.CURSANDO}
        opcoes = []
        for oficina in regras.oficinas_para_matricular(request.user):
            if oficina.pk in cursando:
                continue
            opcoes.append({
                'oficina': oficina,
                'vagas_livres': max(oficina.vagas - oficina.vagas_ocupadas, 0),
                'conflitos': regras.conflitos_de_horario(aluno, oficina),
            })
        return render(request, self.template_name, {
            'aluno': aluno,
            'matriculas': [
                {'matricula': m, 'pode_gerenciar': acesso.pode_gerenciar_escola(request.user, m.escola_id)}
                for m in matriculas
            ],
            'opcoes': opcoes,
            'etapa_atual': 6,
        })

    def post(self, request, pk):
        aluno = self.get_aluno()
        oficina = get_object_or_404(Oficina, pk=request.POST.get('oficina'))
        try:
            regras.matricular(aluno, oficina, request.user)
            messages.success(request, f'Matriculado(a) em "{oficina.nome}".')
        except regras.MatriculaRecusada as erro:
            messages.error(request, str(erro))
        return redirect('matriculas:aluno', pk=aluno.pk)


class AlterarSituacaoView(PerfilRequiredMixin, View):
    """Concluir ou registrar desistência (com data). A regra de quem pode está em regras.py."""

    http_method_names = ['post']
    acao = None  # 'concluir' | 'desistir'

    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)

    def post(self, request, pk):
        # De outra unidade = 404 (filtrar_por_escola usa matricula.escola).
        matriculas = acesso.filtrar_por_escola(request.user, Matricula.objects.select_related('aluno', 'oficina'))
        matricula = get_object_or_404(matriculas, pk=pk)
        try:
            data = date.fromisoformat(request.POST['data']) if request.POST.get('data') else None
        except ValueError:
            data = None
        try:
            if self.acao == 'concluir':
                regras.concluir(matricula, request.user, data)
                messages.success(request, f'Matrícula de {matricula.aluno.nome} concluída.')
            else:
                regras.registrar_desistencia(matricula, request.user, data)
                messages.success(request, f'Desistência de {matricula.aluno.nome} registrada.')
        except regras.MatriculaRecusada as erro:
            messages.error(request, str(erro))
        return redirecionar(request, reverse('matriculas:oficina', args=[matricula.oficina_id]))
