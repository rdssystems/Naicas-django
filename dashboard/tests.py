from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.tests import criar_aluno, criar_usuario
from core.acesso import NivelAcesso
from escolas.foco import CHAVE_SESSAO
from escolas.models import EscolaNaica
from frequencia.models import Chamada, RegistroAula
from matriculas import regras as regras_matricula
from matriculas.models import Matricula
from oficinas.models import Designacao, TipoOficina
from oficinas.tests import criar_oficina

from . import grafico, indicadores

HOJE = timezone.localdate()
SENHA = 'x'


class BaseDashboardTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alfa = EscolaNaica.objects.create(nome='Naica Alfa')
        cls.beta = EscolaNaica.objects.create(nome='Naica Beta')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord_alfa = criar_usuario('coord_alfa', NivelAcesso.COORDENADOR, cls.alfa)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        periodo = {'data_inicio': HOJE - timedelta(days=60), 'data_fim': HOJE + timedelta(days=60)}
        # Dança (Alfa) acontece HOJE, 2 vagas; Música (Beta) em outro dia.
        outro_dia = (HOJE.weekday() + 1) % 7
        cls.danca = criar_oficina(TipoOficina.objects.create(escola=cls.alfa, nome='Arte'), 'Dança',
                                  dias_semana=[HOJE.weekday()], vagas=2, **periodo)
        cls.musica = criar_oficina(TipoOficina.objects.create(escola=cls.beta, nome='Som'), 'Música',
                                   dias_semana=[outro_dia], vagas=10, **periodo)
        cls.ana = criar_aluno(cls.alfa, 960000001, 'Ana')
        cls.bia = criar_aluno(cls.alfa, 960000002, 'Bia')
        cls.caio = criar_aluno(cls.alfa, 960000003, 'Caio')  # fila de espera (sem matrícula)
        cls.bruno = criar_aluno(cls.beta, 960000004, 'Bruno')
        for aluno in (cls.ana, cls.bia):
            regras_matricula.matricular(aluno, cls.danca, cls.diretor)
        regras_matricula.matricular(cls.bruno, cls.musica, cls.diretor)
        Matricula.objects.update(data_inscricao=HOJE - timedelta(days=50))

    def lancar(self, oficina, data, presencas):
        aula = RegistroAula.objects.create(oficina=oficina, data_aula=data)
        for aluno, valor in presencas.items():
            Chamada.objects.create(registro_aula=aula, matricula=Matricula.objects.get(aluno=aluno, oficina=oficina),
                                   status_presenca=valor)


class PermissoesTests(BaseDashboardTestCase):
    def test_quem_acessa(self):
        url = reverse('dashboard:painel')
        self.assertEqual(self.client.get(url).status_code, 302)  # anônimo -> login
        for user, esperado in ((self.diretor, 200), (self.coord_alfa, 200), (self.monitor, 403)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, esperado, user)

    def test_item_no_menu_so_para_diretor_e_coordenador(self):
        for user, aparece in ((self.diretor, True), (self.coord_alfa, True), (self.monitor, False)):
            self.client.force_login(user)
            home = self.client.get(reverse('core:home'))
            (self.assertContains if aparece else self.assertNotContains)(home, reverse('dashboard:painel'))


class LoginRedirecionaTests(BaseDashboardTestCase):
    def logar(self, username, **extra):
        from django.contrib.auth.models import User
        user = User.objects.get(username=username)
        user.set_password(SENHA)
        user.save()
        return self.client.post(reverse('usuarios:login') + extra.get('query', ''), {'username': username, 'password': SENHA})

    def test_diretor_e_coordenador_caem_no_dashboard(self):
        for username in ('diretor', 'coord_alfa'):
            self.assertRedirects(self.logar(username), reverse('dashboard:painel'), fetch_redirect_response=False)
            self.client.logout()

    def test_monitor_continua_no_inicio(self):
        self.assertRedirects(self.logar('monitor'), reverse('core:home'), fetch_redirect_response=False)

    def test_next_tem_prioridade(self):
        destino = reverse('alunos:lista')
        response = self.logar('diretor', query=f'?next={destino}')
        self.assertRedirects(response, destino, fetch_redirect_response=False)


class RecorteTests(BaseDashboardTestCase):
    def test_visao_geral_soma_a_rede_e_compara_unidades(self):
        dados = indicadores.painel(self.diretor)
        self.assertEqual(dados['alunos']['total'], 4)
        self.assertEqual(dados['ocupacao']['cursando'], 3)
        # A tabela lista TODAS as unidades (inclusive as 10 reais da migração), em ordem alfabética.
        por_nome = {u['escola'].nome: u for u in dados['unidades']}
        self.assertEqual(len(dados['unidades']), EscolaNaica.objects.count())
        alfa, beta = por_nome['Naica Alfa'], por_nome['Naica Beta']
        self.assertEqual((alfa['alunos'], alfa['cursando'], alfa['ocupacao']), (3, 2, 100))
        self.assertEqual((beta['alunos'], beta['cursando'], beta['ocupacao']), (1, 1, 10))
        self.assertIsNone(por_nome['Naica Tibery']['ocupacao'])  # sem oficinas

    def test_diretor_dentro_da_unidade_ve_so_ela_sem_tabela(self):
        self.client.force_login(self.diretor)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.beta.pk
        sessao.save()
        response = self.client.get(reverse('dashboard:painel'))
        self.assertEqual(response.context['alunos']['total'], 1)
        self.assertNotIn('unidades', response.context)
        self.assertContains(response, 'Naica Beta')

    def test_coordenador_ve_so_a_propria_unidade(self):
        dados = indicadores.painel(self.coord_alfa)
        self.assertEqual(dados['alunos']['total'], 3)
        self.assertEqual(dados['ocupacao']['cursando'], 2)
        self.assertNotIn('unidades', dados)


class IndicadoresTests(BaseDashboardTestCase):
    def test_alunos_incompletos_pendencias_e_fila(self):
        dados = indicadores.alunos(indicadores.recorte_da_unidade(self.alfa))
        self.assertEqual(dados['fila_espera'], 1)  # Caio
        self.assertEqual(dados['incompletos'], 3)  # helpers criam só a etapa 1
        self.assertEqual(dict(dados['pendencias'])['Responsável'], 3)

    def test_ocupacao_e_lotadas(self):
        dados = indicadores.ocupacao(indicadores.recorte_da_unidade(self.alfa))
        self.assertEqual((dados['ocupadas'], dados['vagas'], dados['percentual']), (2, 2, 100))
        self.assertEqual([o.nome for o in dados['lotadas']], ['Dança'])

    def test_frequencia_30_dias_semanas_e_risco(self):
        for dias in (1, 8, 15):
            self.lancar(self.danca, HOJE - timedelta(days=dias), {self.ana: 'P', self.bia: 'F'})
        self.lancar(self.danca, HOJE - timedelta(days=22), {self.ana: 'J', self.bia: 'F'})
        dados = indicadores.frequencia(indicadores.recorte_da_unidade(self.alfa), HOJE)
        self.assertEqual(dados['percentual'], 50)  # 4 de 8 (J conta como presença)
        self.assertEqual(len(dados['semanas']), 8)
        self.assertEqual([m.aluno.nome for m in dados['risco']], ['Bia'])
        self.assertEqual(dados['risco'][0].percentual, 0)

    def test_operacao_de_hoje(self):
        recorte = indicadores.recorte_da_unidade(self.alfa)
        hoje = indicadores.operacao_de_hoje(recorte, HOJE)
        self.assertEqual([o.nome for o in hoje['chamada_pendente']], ['Dança'])
        self.assertEqual([o.nome for o in hoje['sem_monitor']], ['Dança'])
        Designacao.objects.create(oficina=self.danca, monitor=self.monitor)
        self.lancar(self.danca, HOJE, {self.ana: 'P', self.bia: 'P'})
        hoje = indicadores.operacao_de_hoje(recorte, HOJE)
        self.assertEqual((hoje['chamada_pendente'], hoje['sem_monitor']), ([], []))

    def test_monitor_escalado_em_outro_dia_nao_cobre_hoje(self):
        outro_dia = (HOJE.weekday() + 1) % 7
        self.danca.dias_semana = [HOJE.weekday(), outro_dia]
        self.danca.save()
        Designacao.objects.create(oficina=self.danca, monitor=self.monitor, dias_semana=[outro_dia])
        hoje = indicadores.operacao_de_hoje(indicadores.recorte_da_unidade(self.alfa), HOJE)
        self.assertEqual([o.nome for o in hoje['sem_monitor']], ['Dança'])


class GraficoTests(TestCase):
    def semana(self, dias_atras, percentual, chamadas=10):
        return {'inicio': HOJE - timedelta(days=dias_atras), 'percentual': percentual, 'chamadas': chamadas}

    def test_semana_sem_chamada_interrompe_a_linha(self):
        semanas = [self.semana(21, 80), self.semana(14, None, 0), self.semana(7, 60), self.semana(0, 90)]
        g = grafico.frequencia_semanal(semanas, 75)
        self.assertEqual(len(g['segmentos']), 2)
        self.assertTrue(g['tem_dados'])
        self.assertIsNone(g['pontos'][1]['y'])

    def test_sem_dados(self):
        g = grafico.frequencia_semanal([self.semana(7, None, 0), self.semana(0, None, 0)], 75)
        self.assertFalse(g['tem_dados'])

    def test_pagina_renderiza_coordenadas_com_ponto(self):
        diretor = criar_usuario('d2', NivelAcesso.DIRETOR)
        escola = EscolaNaica.objects.create(nome='Naica Gama')
        oficina = criar_oficina(TipoOficina.objects.create(escola=escola, nome='T'), 'Teatro',
                                data_inicio=HOJE - timedelta(days=60), data_fim=HOJE + timedelta(days=60))
        aluno = criar_aluno(escola, 970000001, 'Duda')
        regras_matricula.matricular(aluno, oficina, diretor)
        Matricula.objects.update(data_inscricao=HOJE - timedelta(days=50))
        aula = RegistroAula.objects.create(oficina=oficina, data_aula=HOJE - timedelta(days=3))
        Chamada.objects.create(registro_aula=aula, matricula=Matricula.objects.get(aluno=aluno), status_presenca='P')
        self.client.force_login(diretor)
        response = self.client.get(reverse('dashboard:painel'))
        self.assertContains(response, 'Frequência por semana')
        self.assertNotRegex(response.content.decode(), r'(cx|cy|x|y1|points)="\d+,\d+"')
