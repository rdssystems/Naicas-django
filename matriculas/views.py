from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from alunos.views import CadastroAlunoMixin
from core import acesso
from core.mixins import PerfilRequiredMixin
from oficinas.models import AtividadeCronograma


class GestaoOficinaMixin(PerfilRequiredMixin):
    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)

    def get_oficina(self):
        return get_object_or_404(
            acesso.filtrar_por_escola(self.request.user, AtividadeCronograma.objects.all()), pk=self.kwargs['pk'],
        )


class MatriculadosOficinaView(GestaoOficinaMixin, View):
    """Endereço antigo da matrícula: a participação é definida pela turma."""

    def get(self, request, pk):
        return redirect('escalas:detalhe', pk=self.get_oficina().pk)


class MatricularNaOficinaView(MatriculadosOficinaView):
    pass


class EtapaMatriculaView(CadastroAlunoMixin, View):
    """Consulta do cronograma da turma do atendido, sem inscrição individual."""

    def get(self, request, pk):
        aluno = self.get_aluno()
        oficinas = acesso.filtrar_por_escola(request.user, AtividadeCronograma.objects.filter(
            escola=aluno.escola, turno=aluno.turno,
            turmas__contains=[aluno.turma] if aluno.turma else [],
            ativo=True, oficina__arquivada=False,
        )).order_by('horario', 'oficina__nome') if aluno.turno and aluno.turma else AtividadeCronograma.objects.none()
        return render(request, 'matriculas/aluno_matriculas.html', {
            'aluno': aluno, 'oficinas': oficinas, 'etapa_atual': 6,
        })


class AlterarSituacaoView(GestaoOficinaMixin, View):
    # URL mantida para responder 405 aos antigos formulários, sem alterar históricos.
    http_method_names = []
    acao = None
