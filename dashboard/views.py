from django.db.models import Count, Q
from django.views.generic import TemplateView

from alunos.models import Aluno
from core import acesso
from core.mixins import PerfilRequiredMixin
from escolas.models import EscolaNaica
from frequencia.models import Chamada
from matriculas.models import Matricula
from oficinas.models import Oficina


class DashboardView(PerfilRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)

    @staticmethod
    def indicadores(escola=None):
        alunos = Aluno.objects.all()
        oficinas = Oficina.objects.all()
        matriculas = Matricula.objects.filter(status=Matricula.Status.CURSANDO)
        if escola is not None:
            alunos = alunos.filter(escola=escola)
            oficinas = oficinas.filter(escola=escola)
            matriculas = matriculas.filter(escola=escola)

        oficinas_ativas = oficinas.exclude(
            status__in=[Oficina.Status.CONCLUIDO, Oficina.Status.ARQUIVADO]
        )
        chamadas = Chamada.objects.filter(registro_aula__oficina__in=oficinas)
        presencas = chamadas.aggregate(
            total=Count('pk'),
            presentes=Count('pk', filter=Q(status_presenca=Chamada.Presenca.PRESENTE)),
        )
        total_chamadas = presencas['total']
        return {
            'alunos': alunos.count(),
            'oficinas': oficinas_ativas.count(),
            'matriculas': matriculas.count(),
            'frequencia': round(100 * presencas['presentes'] / total_chamadas) if total_chamadas else None,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if acesso.is_diretor(user):
            foco = acesso.escola_em_foco(user)
            context['indicadores'] = self.indicadores(foco)
            context['unidades'] = (
                [{'escola': escola, **self.indicadores(escola)} for escola in EscolaNaica.objects.all()]
                if foco is None else []
            )
        else:
            escola = acesso.escola_do_usuario(user)
            context['indicadores'] = self.indicadores(escola)
            context['unidades'] = []
        return context
