from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from core import acesso
from core.mixins import PerfilRequiredMixin
from core.validators import so_digitos
from escolas.models import EscolaNaica

from .forms import (
    AlunoForm, ContatoEmergenciaFormSet, EnderecoForm, FichaSaudeForm, MembroFamiliarFormSet, ResponsavelForm,
)
from .models import Aluno, AlunoResponsavel, FichaSaude, Responsavel


class CadastroAlunoMixin(PerfilRequiredMixin):
    """Cadastro de aluno: só Diretor e Coordenador; Monitor não acessa."""

    def tem_permissao(self, user):
        return acesso.is_diretor(user) or acesso.is_coordenador(user)

    def alunos_visiveis(self):
        return Aluno.objects.visiveis_para(self.request.user)

    def get_aluno(self):
        return get_object_or_404(self.alunos_visiveis().select_related('escola'), pk=self.kwargs['pk'])


class AlunoListView(CadastroAlunoMixin, ListView):
    template_name = 'alunos/aluno_list.html'
    context_object_name = 'alunos'
    paginate_by = 25

    def get_queryset(self):
        qs = self.alunos_visiveis().select_related('escola', 'endereco', 'ficha_saude').prefetch_related(
            'responsaveis_vinculos', 'contatos_emergencia'
        )
        params = self.request.GET
        if busca := params.get('q', '').strip():
            filtro = Q(nome__icontains=busca) | Q(nome_mae__icontains=busca)
            if digitos := so_digitos(busca):
                filtro |= Q(cpf__startswith=digitos)
            qs = qs.filter(filtro)
        if (escola := params.get('escola')) and acesso.is_diretor(self.request.user):
            qs = qs.filter(escola_id=escola)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if acesso.is_diretor(self.request.user):
            context['escolas'] = EscolaNaica.objects.all()
        filtros = self.request.GET.copy()
        filtros.pop('page', None)
        context['filtros_querystring'] = filtros.urlencode()
        return context


class AlunoDetailView(CadastroAlunoMixin, DetailView):
    template_name = 'alunos/aluno_detail.html'
    context_object_name = 'aluno'

    def get_object(self, queryset=None):
        return self.get_aluno()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['vinculos'] = self.object.responsaveis_vinculos.select_related('responsavel')
        context['membros'] = self.object.membros_familia.all()
        context['contatos'] = self.object.contatos_emergencia.all()
        # Dado sensível: só vai para o template se o papel puder ver.
        user = self.request.user
        ficha = getattr(self.object, 'ficha_saude', None)
        context['pode_ver_saude_completa'] = acesso.pode_ver_saude_completa(user)
        context['pode_ver_saude_emergencia'] = acesso.pode_ver_saude_emergencia(user)
        context['ficha'] = ficha if context['pode_ver_saude_emergencia'] else None
        return context


class EtapaDadosView(CadastroAlunoMixin, View):
    """Etapa 1: dados do aluno + endereço. Sem pk = cadastro novo."""

    template_name = 'alunos/etapa_dados.html'

    def get_forms(self, data=None):
        aluno = self.get_aluno() if 'pk' in self.kwargs else None
        endereco = getattr(aluno, 'endereco', None) if aluno else None
        return (
            AlunoForm(data, instance=aluno, user=self.request.user),
            EnderecoForm(data, instance=endereco, prefix='end'),
            aluno,
        )

    def render(self, aluno_form, endereco_form, aluno):
        existente = aluno_form.aluno_existente
        return render(self.request, self.template_name, {
            'aluno': aluno,
            'form': aluno_form,
            'endereco_form': endereco_form,
            'aluno_existente_visivel': (
                existente if existente and self.alunos_visiveis().filter(pk=existente.pk).exists() else None
            ),
            'etapa_atual': 1,
        })

    def get(self, request, *args, **kwargs):
        return self.render(*self.get_forms())

    def post(self, request, *args, **kwargs):
        aluno_form, endereco_form, aluno = self.get_forms(request.POST)
        # Valida os dois antes de salvar qualquer um.
        if not (aluno_form.is_valid() & endereco_form.is_valid()):
            return self.render(aluno_form, endereco_form, aluno)
        with transaction.atomic():
            novo = aluno is None
            aluno = aluno_form.save(commit=False)
            if novo:
                aluno.criado_por = request.user
            aluno.save()
            endereco = endereco_form.save(commit=False)
            endereco.aluno = aluno
            endereco.save()
        if novo:
            messages.success(request, f'Aluno "{aluno.nome}" cadastrado. Agora informe o responsável.')
            return redirect('alunos:etapa_responsaveis', pk=aluno.pk)
        messages.success(request, 'Dados do aluno atualizados.')
        return redirect('alunos:detalhe', pk=aluno.pk)


class EtapaResponsaveisView(CadastroAlunoMixin, View):
    """Etapa 2: lista os responsáveis vinculados e adiciona um novo (ou existente pelo CPF)."""

    template_name = 'alunos/etapa_responsaveis.html'

    def render(self, aluno, form):
        return render(self.request, self.template_name, {
            'aluno': aluno,
            'form': form,
            'vinculos': aluno.responsaveis_vinculos.select_related('responsavel'),
            'etapa_atual': 2,
        })

    def get(self, request, pk):
        aluno = self.get_aluno()
        return self.render(aluno, ResponsavelForm(aluno=aluno))

    def post(self, request, pk):
        aluno = self.get_aluno()
        cpf = so_digitos(request.POST.get('cpf'))
        existente = Responsavel.objects.filter(cpf=cpf).first() if cpf else None
        form = ResponsavelForm(request.POST, instance=existente, aluno=aluno)
        if not form.is_valid():
            return self.render(aluno, form)
        with transaction.atomic():
            responsavel = form.save()
        messages.success(request, f'Responsável "{responsavel.nome}" vinculado ao aluno.')
        return redirect('alunos:etapa_responsaveis', pk=aluno.pk)


class EtapaFamiliaView(CadastroAlunoMixin, View):
    """
    Etapa 3: composição familiar (opcional) e contatos de emergência (mínimo 2).

    Os responsáveis da etapa 2 entram pré-preenchidos na composição familiar
    na primeira visita (etapa nunca salva) e, depois disso, só quando o
    usuário pede (?incluir_responsaveis=1) — para não reaparecer quem foi
    removido de propósito.
    """

    template_name = 'alunos/etapa_familia.html'

    def get_formsets(self, aluno, data=None, pre_preencher=()):
        membros = MembroFamiliarFormSet(
            data, instance=aluno, prefix='membros', form_kwargs={'aluno': aluno},
            initial=[
                {
                    'responsavel': v.responsavel_id,
                    'nome': v.responsavel.nome,
                    'parentesco': v.grau_parentesco,
                    'data_nascimento': v.responsavel.data_nascimento,
                }
                for v in pre_preencher
            ],
        )
        # Linhas extras para os pré-preenchidos (o formset só mostra
        # `initial` em formulários extras).
        membros.extra = len(pre_preencher)
        contatos = ContatoEmergenciaFormSet(data, instance=aluno, prefix='contatos')
        return membros, contatos

    def render(self, aluno, membros, contatos, pre_preenchidos=()):
        faltando = [] if pre_preenchidos else aluno.vinculos_fora_da_familia()
        return render(self.request, self.template_name, {
            'aluno': aluno, 'membros_formset': membros, 'contatos_formset': contatos, 'etapa_atual': 3,
            'pre_preenchidos': pre_preenchidos, 'responsaveis_faltando': faltando,
        })

    def get(self, request, pk):
        aluno = self.get_aluno()
        nunca_salva = not aluno.membros_familia.exists() and not aluno.contatos_emergencia.exists()
        pre_preencher = []
        if nunca_salva or request.GET.get('incluir_responsaveis'):
            pre_preencher = aluno.vinculos_fora_da_familia()
        membros, contatos = self.get_formsets(aluno, pre_preencher=pre_preencher)
        return self.render(aluno, membros, contatos, pre_preencher)

    def post(self, request, pk):
        aluno = self.get_aluno()
        membros, contatos = self.get_formsets(aluno, request.POST)
        if not (membros.is_valid() & contatos.is_valid()):
            return self.render(aluno, membros, contatos)
        with transaction.atomic():
            membros.save()
            contatos.save()
        messages.success(request, 'Família e contatos de emergência salvos.')
        return redirect('alunos:detalhe', pk=aluno.pk)


class EtapaSaudeView(CadastroAlunoMixin, View):
    """Etapa 4: ficha de saúde (LGPD: papel checado em core.acesso, não só no template)."""

    template_name = 'alunos/etapa_saude.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not acesso.pode_ver_saude_completa(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def render(self, aluno, form):
        return render(self.request, self.template_name, {'aluno': aluno, 'form': form, 'etapa_atual': 4})

    def get(self, request, pk):
        aluno = self.get_aluno()
        return self.render(aluno, FichaSaudeForm(instance=getattr(aluno, 'ficha_saude', None)))

    def post(self, request, pk):
        aluno = self.get_aluno()
        ficha = getattr(aluno, 'ficha_saude', None) or FichaSaude(aluno=aluno)
        form = FichaSaudeForm(request.POST, instance=ficha)
        if not form.is_valid():
            return self.render(aluno, form)
        ficha = form.save(commit=False)
        ficha.atualizado_por = request.user
        ficha.save()
        messages.success(request, 'Ficha de saúde salva.')
        return redirect('alunos:detalhe', pk=aluno.pk)


class ResponsavelEditarView(CadastroAlunoMixin, View):
    template_name = 'alunos/responsavel_form.html'

    def get_vinculo(self, aluno):
        return get_object_or_404(
            AlunoResponsavel.objects.select_related('responsavel'), pk=self.kwargs['vinculo_pk'], aluno=aluno
        )

    def render(self, aluno, vinculo, form):
        return render(self.request, self.template_name, {
            'aluno': aluno, 'vinculo': vinculo, 'form': form, 'etapa_atual': 2,
            'outros_alunos': vinculo.responsavel.alunos_vinculos.exclude(aluno=aluno).count(),
        })

    def get(self, request, pk, vinculo_pk):
        aluno = self.get_aluno()
        vinculo = self.get_vinculo(aluno)
        form = ResponsavelForm(instance=vinculo.responsavel, aluno=aluno, vinculo=vinculo)
        return self.render(aluno, vinculo, form)

    def post(self, request, pk, vinculo_pk):
        aluno = self.get_aluno()
        vinculo = self.get_vinculo(aluno)
        form = ResponsavelForm(request.POST, instance=vinculo.responsavel, aluno=aluno, vinculo=vinculo)
        if not form.is_valid():
            return self.render(aluno, vinculo, form)
        with transaction.atomic():
            form.save()
        messages.success(request, 'Responsável atualizado.')
        return redirect('alunos:etapa_responsaveis', pk=aluno.pk)


class ResponsavelRemoverView(CadastroAlunoMixin, View):
    """Remove só o vínculo; o cadastro do responsável continua na rede."""

    http_method_names = ['post']

    def post(self, request, pk, vinculo_pk):
        aluno = self.get_aluno()
        vinculo = get_object_or_404(AlunoResponsavel, pk=vinculo_pk, aluno=aluno)
        nome = vinculo.responsavel.nome
        vinculo.delete()
        messages.success(request, f'{nome} não é mais responsável por este aluno.')
        return redirect('alunos:etapa_responsaveis', pk=aluno.pk)


class BuscarResponsavelView(CadastroAlunoMixin, View):
    """JSON para pré-preencher o formulário ao digitar um CPF já cadastrado na rede."""

    CAMPOS = [
        'nome', 'celular', 'email', 'documento_numero', 'documento_orgao_expedidor', 'documento_uf',
        'ctps_numero', 'ctps_serie', 'qual_beneficio',
    ]
    CAMPOS_DATA = ['data_nascimento', 'documento_data_expedicao']
    CAMPOS_SIM_NAO = ['trabalha', 'carteira_assinada', 'contribui_previdencia', 'recebe_beneficio']

    def get(self, request):
        cpf = so_digitos(request.GET.get('cpf'))
        responsavel = Responsavel.objects.filter(cpf=cpf).first() if len(cpf) == 11 else None
        if responsavel is None:
            return JsonResponse({'encontrado': False})
        dados = {campo: getattr(responsavel, campo) for campo in self.CAMPOS}
        dados.update({campo: getattr(responsavel, campo).isoformat() for campo in self.CAMPOS_DATA})
        dados.update({
            campo: ('' if getattr(responsavel, campo) is None else str(getattr(responsavel, campo)))
            for campo in self.CAMPOS_SIM_NAO
        })
        return JsonResponse({'encontrado': True, 'dados': dados})
