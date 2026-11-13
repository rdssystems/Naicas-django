from datetime import time

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.acesso import NivelAcesso
from escolas.foco import CHAVE_SESSAO
from escolas.models import EscolaNaica
from usuarios.models import Profile

from .forms import AtividadeCronogramaForm, OficinaForm
from .models import AtividadeCronograma, Oficina


def criar_usuario(username, nivel, escola=None, **extra):
    user = User.objects.create_user(username=username, password='x', first_name=username, **extra)
    Profile.objects.create(user=user, nivel_acesso=nivel, escola=escola)
    return user


def criar_tag(escola, nome, **kwargs):
    """Adapta as fixtures antigas para o catálogo compartilhado."""
    oficina, _ = Oficina.objects.get_or_create(nome=nome, defaults=kwargs)
    oficina.escola = escola
    return oficina


def criar_oficina(tipo, nome=None, **kwargs):
    """Cria um vínculo de cronograma para as fixtures de outros apps."""
    tag = tipo
    if nome and nome != tipo.nome:
        tag, _ = Oficina.objects.get_or_create(nome=nome)
    status = kwargs.pop('status', 'ABERTA')
    for campo in ('data_inicio', 'data_fim', 'vagas', 'carga_horaria'):
        kwargs.pop(campo, None)
    dados = dict(escola=tipo.escola, oficina=tag, turno='MANHA',
                 horario=time(8), horario_fim=time(10), dias_semana=[0, 2],
                 turmas=['A'], ativo=status in ('ABERTA', 'EM_ANDAMENTO'))
    dados.update(kwargs)
    return AtividadeCronograma.objects.create(**dados)


class CatalogoOficinasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = EscolaNaica.objects.create(nome='Alfa')
        cls.b = EscolaNaica.objects.create(nome='Beta')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord = criar_usuario('coord', NivelAcesso.COORDENADOR, cls.a)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.arte = Oficina.objects.create(nome='Arte', cor='#c8471f')
        cls.esporte = Oficina.objects.create(nome='Educação Física', cor='#2e7a4c')
        cls.horario = AtividadeCronograma.objects.create(
            escola=cls.a, oficina=cls.arte, turno='MANHA', turmas=['A'],
            dias_semana=[0, 2], horario=time(8), horario_fim=time(10),
        )

    def test_diretor_cria_oficina_unica_disponivel_em_toda_rede(self):
        self.client.force_login(self.diretor)
        resposta = self.client.post(reverse('oficinas:criar'), {'nome': 'Música', 'cor': '#2b3a8c'})
        self.assertRedirects(resposta, reverse('oficinas:lista'))
        self.assertTrue(Oficina.objects.filter(nome='Música').exists())
        self.client.force_login(self.coord)
        resposta = self.client.get(reverse('oficinas:lista'))
        self.assertContains(resposta, 'Música')
        self.assertNotContains(resposta, 'Nova oficina')
        self.assertNotContains(resposta, 'Tipos de oficina')

    def test_coordenador_e_monitor_nao_gerenciam_catalogo_nem_por_post(self):
        for user in (self.coord, self.monitor):
            self.client.force_login(user)
            for nome, args in (('criar', []), ('editar', [self.arte.pk]),
                               ('excluir', [self.arte.pk]), ('arquivar', [self.arte.pk])):
                url = reverse(f'oficinas:{nome}', args=args)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {'nome': 'Adulterada'}).status_code, 403)
        self.arte.refresh_from_db()
        self.assertEqual(self.arte.nome, 'Arte')

    def test_catalogo_nao_se_duplica_por_unidade_ou_maiusculas(self):
        form = OficinaForm(data={'nome': ' arte ', 'cor': '#ffffff'})
        self.assertFalse(form.is_valid())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Oficina.objects.create(nome='ARTE')

    def test_oficina_sem_periodo_ou_carga_horaria(self):
        self.assertEqual(set(OficinaForm().fields), {'nome', 'cor'})
        campos = {campo.name for campo in AtividadeCronograma._meta.fields}
        for campo in ('data_inicio', 'data_fim', 'carga_horaria', 'tipo_oficina', 'vagas'):
            self.assertNotIn(campo, campos)

    def test_arquivar_e_reativar_preserva_vinculos(self):
        from escalas.regras import agenda_semanal
        self.client.force_login(self.diretor)
        self.client.post(reverse('oficinas:arquivar', args=[self.arte.pk]))
        self.arte.refresh_from_db()
        self.assertTrue(self.arte.arquivada)
        self.assertTrue(agenda_semanal(self.coord)['vazia'])
        self.assertTrue(AtividadeCronograma.objects.filter(pk=self.horario.pk).exists())
        self.client.post(reverse('oficinas:arquivar', args=[self.arte.pk]))
        self.assertFalse(agenda_semanal(self.coord)['vazia'])

    def test_excluir_exige_post_e_preserva_historico(self):
        from alunos.tests import criar_aluno
        from frequencia.models import ChamadaGeral, RegistroAula
        from matriculas.models import Matricula
        from django.utils import timezone
        aluno = criar_aluno(self.a, 955000001)
        matricula = Matricula.objects.create(aluno=aluno, oficina=self.horario)
        RegistroAula.objects.create(oficina=self.horario, data_aula=timezone.localdate())
        ChamadaGeral.objects.create(escola=self.a, aluno=aluno, data=timezone.localdate(), status_presenca='P')
        self.client.force_login(self.diretor)
        url = reverse('oficinas:excluir', args=[self.arte.pk])
        self.assertContains(self.client.get(url), 'Excluir Arte?')
        self.assertTrue(Oficina.objects.filter(pk=self.arte.pk).exists())
        self.assertRedirects(self.client.post(url), reverse('oficinas:lista'))
        self.horario.refresh_from_db()
        self.assertIsNone(self.horario.oficina_id)
        self.assertEqual(self.horario.nome, 'Arte')
        self.assertTrue(Matricula.objects.filter(pk=matricula.pk).exists())
        self.assertEqual(ChamadaGeral.objects.count(), 1)
        from escalas.regras import agenda_semanal
        self.assertTrue(agenda_semanal(self.coord)['vazia'])

    def test_diretor_em_foco_mantem_catalogo_global_e_escopo_dos_horarios(self):
        AtividadeCronograma.objects.create(
            escola=self.b, oficina=self.esporte, turno='TARDE', turmas=['C'],
            dias_semana=[1], horario=time(13), horario_fim=time(15),
        )
        self.client.force_login(self.diretor)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.a.pk
        sessao.save()
        resposta = self.client.get(reverse('oficinas:lista'))
        self.assertContains(resposta, 'Educação Física')
        oficina = next(o for o in resposta.context['oficinas'] if o.pk == self.esporte.pk)
        self.assertEqual(oficina.total_horarios, 0)

    def test_rotas_de_tipos_nao_criam_catalogo_paralelo(self):
        self.client.force_login(self.diretor)
        self.assertRedirects(self.client.get(reverse('oficinas:tipos')), reverse('oficinas:lista'))
        self.assertEqual(self.client.post(reverse('oficinas:tipo_criar'), {'nome': 'Outra'}).status_code, 405)

    def test_cor_invalida_e_recusada(self):
        self.assertFalse(OficinaForm(data={'nome': 'Música', 'cor': 'javascript:alert(1)'}).is_valid())
