from datetime import timedelta

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from dashboard import indicadores
from escolas.foco import CHAVE_SESSAO
from frequencia.models import ChamadaGeral

from .models import Aluno, Ocorrencia
from .tests import BaseAlunosTestCase, criar_aluno


class StatusAlunoTests(BaseAlunosTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.inativo = criar_aluno(cls.escola_a, 100000003, 'Aaron inativo')
        cls.outro_inativo = criar_aluno(cls.escola_a, 100000004, 'Beatriz inativa')
        Aluno.objects.filter(pk=cls.inativo.pk).update(status=Aluno.Status.INATIVO, turno=None, turma=None)
        Aluno.objects.filter(pk=cls.outro_inativo.pk).update(status=Aluno.Status.INATIVO, turno=None, turma=None)

    def url(self, aluno=None):
        return reverse('alunos:alterar_status', args=[(aluno or self.aluno_a).pk])

    def test_padrao_ativo_e_ficha_em_cada_linha_ativos_primeiro(self):
        self.assertEqual(self.aluno_a.status, Aluno.Status.ATIVO)
        self.client.force_login(self.diretor)
        pagina = self.client.get(reverse('alunos:lista'))
        self.assertEqual(list(pagina.context['alunos']), [self.aluno_a, self.aluno_b, self.inativo, self.outro_inativo])
        self.assertEqual(pagina.context['totais_status'], {'ativos': 2, 'inativos': 2})
        self.assertEqual(pagina.context['alunos_pendentes_classificacao'], 0)
        for aluno in (self.aluno_a, self.aluno_b, self.inativo, self.outro_inativo):
            self.assertContains(pagina, f'aria-label="Visualizar ficha de {aluno.nome}"')
        for rotulo in ('Ativo', 'Inativo', '>Ficha</a>'):
            self.assertContains(pagina, rotulo)

    def test_ordenacao_global_e_filtros_preservados_na_paginacao(self):
        for i in range(24):
            criar_aluno(self.escola_a, 100000100 + i, f'Z ativo {i:02}')
        self.client.force_login(self.diretor)
        primeira = self.client.get(reverse('alunos:lista'), {'q': '', 'escola': self.escola_a.pk})
        self.assertTrue(all(aluno.status == Aluno.Status.ATIVO for aluno in primeira.context['alunos']))
        ultima = self.client.get(reverse('alunos:lista'), {'escola': self.escola_a.pk, 'page': 2})
        self.assertEqual(list(ultima.context['alunos']), [self.inativo, self.outro_inativo])
        self.assertEqual(ultima.context['filtros_querystring'], f'escola={self.escola_a.pk}')
        self.assertContains(ultima, f'escola={self.escola_a.pk}&page=1')
        filtrada = self.client.get(reverse('alunos:lista'), {'q': 'Aaron', 'status': Aluno.Status.INATIVO})
        self.assertEqual(list(filtrada.context['alunos']), [self.inativo])
        self.assertEqual(filtrada.context['totais_status']['ativos'], 0)
        pendentes = self.client.get(reverse('alunos:lista'), {'classificacao': 'pendente'})
        self.assertEqual(list(pendentes.context['alunos']), [])

    def test_gestores_inativam_preservando_dados(self):
        ocorrencia = Ocorrencia.objects.create(aluno=self.aluno_a, autor=self.diretor, descricao='Histórico preservado')
        chamada = ChamadaGeral.objects.create(
            aluno=self.aluno_a, escola=self.escola_a, data=timezone.localdate(), status_presenca='P',
        )
        for user in (self.coord_a, self.diretor):
            self.client.force_login(user)
            resposta = self.client.post(self.url(), {'status': Aluno.Status.INATIVO})
            self.assertRedirects(resposta, reverse('alunos:detalhe', args=[self.aluno_a.pk]))
            self.aluno_a.refresh_from_db()
            self.assertEqual(self.aluno_a.status, Aluno.Status.INATIVO)
            self.assertEqual(self.aluno_a.endereco.cidade, 'Recife')
            self.assertTrue(Ocorrencia.objects.filter(pk=ocorrencia.pk).exists())
            self.assertEqual(ChamadaGeral.objects.get(pk=chamada.pk).status_presenca, 'P')

    def test_ficha_mostra_status_e_acoes_correspondentes(self):
        self.client.force_login(self.coord_a)
        for aluno, status in ((self.aluno_a, 'Ativo'), (self.inativo, 'Inativo'), (self.outro_inativo, 'Inativo')):
            pagina = self.client.get(reverse('alunos:detalhe', args=[aluno.pk]))
            self.assertContains(pagina, status)
            self.assertNotContains(pagina, 'Desligar atendido')
            self.assertNotContains(pagina, 'Reativar atendido')
            if aluno == self.aluno_a:
                self.assertContains(pagina, self.url(aluno))
                self.assertContains(pagina, 'csrfmiddlewaretoken')
                self.assertContains(pagina, 'Inativar atendido')
            else:
                self.assertNotContains(pagina, self.url(aluno))
                self.assertNotContains(pagina, 'Inativar atendido')

    def test_status_invalido_e_get_nao_alteram_aluno(self):
        self.client.force_login(self.coord_a)
        self.assertEqual(self.client.get(self.url()).status_code, 405)
        for dados in ({}, {'status': ''}, {'status': 'EXCLUIDO'}, {'status': 'DESLIGADO'}, {'status': 'ATIVO'}):
            self.client.post(self.url(), dados)
            self.aluno_a.refresh_from_db()
            self.assertEqual(self.aluno_a.status, Aluno.Status.ATIVO)
        self.client.post(self.url(self.inativo), {'status': 'ATIVO'})
        self.inativo.refresh_from_db()
        self.assertEqual(self.inativo.status, Aluno.Status.INATIVO)

    def test_alteracao_exige_gestor_e_respeita_unidade_e_foco(self):
        self.assertEqual(self.client.post(self.url(), {'status': 'INATIVO'}).status_code, 302)
        for user, esperado in ((self.monitor, 403), (self.coord_b, 404)):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url(), {'status': 'INATIVO'}).status_code, esperado)
        self.client.force_login(self.diretor)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.escola_b.pk
        sessao.save()
        self.assertEqual(self.client.post(self.url(), {'status': 'INATIVO'}).status_code, 404)
        self.aluno_a.refresh_from_db()
        self.assertEqual(self.aluno_a.status, Aluno.Status.ATIVO)

    def test_alteracao_exige_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.coord_a)
        self.assertEqual(cliente.post(self.url(), {'status': 'INATIVO'}).status_code, 403)
        cliente.get(reverse('alunos:detalhe', args=[self.aluno_a.pk]))
        token = cliente.cookies['csrftoken'].value
        self.assertEqual(cliente.post(self.url(), {'status': 'INATIVO', 'csrfmiddlewaretoken': token}).status_code, 302)
        self.aluno_a.refresh_from_db()
        self.assertEqual(self.aluno_a.status, Aluno.Status.INATIVO)

    def test_painel_conta_so_ativos_na_rede_unidade_e_filtros(self):
        for user, total in ((self.diretor, 2), (self.coord_a, 1)):
            self.client.force_login(user)
            for params in ({}, {'sexo': 'F'}):
                pagina = self.client.get(reverse('dashboard:painel'), params)
                self.assertEqual(pagina.context['alunos']['total'], total)
                self.assertEqual(pagina.context['alunos']['incompletos'], total)
                self.assertEqual(pagina.context['alunos']['classificacao_pendente'], 0)
                self.assertEqual(sum(item['pendentes'] for item in pagina.context['operacao']['chamada_pendente']), total)
                if params:
                    self.assertTrue(all(a.status == Aluno.Status.ATIVO for a in pagina.context['alunos_encontrados']))
        por_unidade = {linha['escola'].pk: linha['alunos'] for linha in indicadores.por_unidade(timezone.localdate())}
        self.assertEqual(por_unidade[self.escola_a.pk], 1)
        self.assertEqual(por_unidade[self.escola_b.pk], 1)
        self.assertEqual(sum(por_unidade.values()), 2)
        self.client.force_login(self.diretor)
        self.client.post(self.url(), {'status': 'INATIVO'})
        self.assertEqual(self.client.get(reverse('dashboard:painel')).context['alunos']['total'], 1)
        self.client.post(self.url(), {'status': 'ATIVO'})
        self.assertEqual(self.client.get(reverse('dashboard:painel')).context['alunos']['total'], 1)

    def test_chamada_so_exige_ativos_e_mantem_historico_corrigivel(self):
        self.client.force_login(self.coord_a)
        url = reverse('frequencia:chamada_naica')
        hoje = timezone.localdate()
        for aluno in (self.inativo, self.outro_inativo):
            ChamadaGeral.objects.create(
                aluno=aluno, escola=self.escola_a, data=hoje - timedelta(days=1), status_presenca='P',
            )
        pagina = self.client.get(url)
        self.assertEqual(pagina.context['total_alunos'], 1)
        self.assertNotContains(pagina, self.inativo.nome)
        self.assertNotContains(pagina, self.outro_inativo.nome)
        resposta = self.client.post(url, {
            'data': hoje.isoformat(), f'presenca_{self.aluno_a.pk}': 'P',
            f'presenca_{self.inativo.pk}': 'F', f'presenca_{self.outro_inativo.pk}': 'F',
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(list(ChamadaGeral.objects.filter(data=hoje).values_list('aluno_id', flat=True)), [self.aluno_a.pk])
        ontem = (hoje - timedelta(days=1)).isoformat()
        historico = self.client.get(url, {'data': ontem})
        self.assertContains(historico, self.inativo.nome)
        self.assertContains(historico, self.outro_inativo.nome)
        resposta = self.client.post(url, {
            'data': ontem, f'presenca_{self.aluno_a.pk}': 'P',
            f'presenca_{self.inativo.pk}': 'J', f'presenca_{self.outro_inativo.pk}': 'P',
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(ChamadaGeral.objects.get(aluno=self.inativo).status_presenca, 'J')
