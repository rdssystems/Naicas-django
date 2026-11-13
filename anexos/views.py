from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from alunos.models import Aluno
from alunos.views import CadastroAlunoMixin
from core.mixins import DiretorRequiredMixin

from .etapa import tipos_obrigatorios_pendentes
from .forms import EnvioAnexoForm, TipoDocumentoForm
from .models import Anexo, TipoDocumento


class AnexosAlunoView(CadastroAlunoMixin, View):
    """Etapa 5: o que já foi enviado e o que falta, cruzando com TipoDocumento.obrigatorio."""

    template_name = 'anexos/aluno_anexos.html'

    def render(self, aluno, form_com_erro=None, tipo_com_erro=None):
        anexos = list(aluno.anexos.select_related('tipo_documento', 'enviado_por'))
        por_tipo = {}
        for anexo in anexos:
            por_tipo.setdefault(anexo.tipo_documento_id, []).append(anexo)
        linhas = [
            {
                'tipo': tipo,
                'anexos': por_tipo.pop(tipo.pk, []),
                'form': form_com_erro if tipo.pk == tipo_com_erro else None,
            }
            for tipo in TipoDocumento.objects.filter(ativo=True)
        ]
        # Arquivos de tipos desativados continuam visíveis (e removíveis).
        inativos = [anexo for lista in por_tipo.values() for anexo in lista]
        return render(self.request, self.template_name, {
            'aluno': aluno,
            'linhas': linhas,
            'anexos_tipos_inativos': inativos,
            'pendentes': tipos_obrigatorios_pendentes(aluno),
            'etapa_atual': 5,
        })

    def get(self, request, pk):
        return self.render(self.get_aluno())

    def post(self, request, pk):
        aluno = self.get_aluno()
        form = EnvioAnexoForm(request.POST, request.FILES)
        if not form.is_valid():
            tipo = request.POST.get('tipo_documento', '')
            return self.render(aluno, form, int(tipo) if tipo.isdigit() else None)
        arquivo = form.cleaned_data['arquivo']
        Anexo.objects.create(
            aluno=aluno,
            tipo_documento=form.cleaned_data['tipo_documento'],
            arquivo=arquivo,
            nome_original=arquivo.name[:255],
            tamanho=arquivo.size,
            enviado_por=request.user,
        )
        messages.success(request, f'"{arquivo.name}" enviado.')
        return redirect('anexos:aluno', pk=aluno.pk)


class AnexoMixin(CadastroAlunoMixin):
    """Anexo só é encontrado se o atendido dele for visível para o usuário."""

    def get_anexo(self):
        return get_object_or_404(
            Anexo.objects.select_related('aluno', 'tipo_documento'),
            pk=self.kwargs['anexo_pk'],
            aluno__in=Aluno.objects.visiveis_para(self.request.user),
        )


class AnexoArquivoView(AnexoMixin, View):
    """Entrega o arquivo (inline) só para quem pode ver o atendido. Nunca há link público."""

    def get(self, request, anexo_pk):
        anexo = self.get_anexo()
        try:
            arquivo = anexo.arquivo.open('rb')
        except FileNotFoundError:
            raise Http404('Arquivo não encontrado no armazenamento.')
        response = FileResponse(arquivo, content_type=anexo.content_type, filename=anexo.nome_original)
        response['Content-Disposition'] = response['Content-Disposition'].replace('attachment', 'inline', 1)
        response['Cache-Control'] = 'private, no-store'
        return response


class AnexoExcluirView(AnexoMixin, View):
    http_method_names = ['post']

    def post(self, request, anexo_pk):
        anexo = self.get_anexo()
        aluno_pk, nome = anexo.aluno_id, anexo.nome_original
        anexo.delete()  # o arquivo é apagado do disco pelo sinal post_delete (apps.py)
        messages.success(request, f'"{nome}" removido.')
        return redirect('anexos:aluno', pk=aluno_pk)


# --- Tipos de documento (só Diretor) ---

class TipoDocumentoListView(DiretorRequiredMixin, ListView):
    template_name = 'anexos/tipo_list.html'
    context_object_name = 'tipos'
    queryset = TipoDocumento.objects.annotate(total_anexos=Count('anexos'))


class TipoDocumentoFormMixin:
    model = TipoDocumento
    form_class = TipoDocumentoForm
    template_name = 'anexos/tipo_form.html'
    success_url = reverse_lazy('anexos:tipos')


class TipoDocumentoCreateView(DiretorRequiredMixin, TipoDocumentoFormMixin, CreateView):
    def form_valid(self, form):
        messages.success(self.request, f'Tipo "{form.instance.nome}" cadastrado.')
        return super().form_valid(form)


class TipoDocumentoUpdateView(DiretorRequiredMixin, TipoDocumentoFormMixin, UpdateView):
    context_object_name = 'tipo'

    def form_valid(self, form):
        messages.success(self.request, f'Tipo "{form.instance.nome}" atualizado.')
        return super().form_valid(form)


class TipoDocumentoExcluirView(DiretorRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        tipo = get_object_or_404(TipoDocumento, pk=pk)
        try:
            tipo.delete()
            messages.success(request, f'Tipo "{tipo.nome}" excluído.')
        except ProtectedError:
            messages.error(request, f'O tipo "{tipo.nome}" tem arquivos enviados. Desative-o em vez de excluir.')
        return redirect('anexos:tipos')
