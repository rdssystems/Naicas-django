from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.tests import criar_aluno, criar_usuario
from alunos.models import Aluno
from core.acesso import NivelAcesso
from escolas.foco import CHAVE_SESSAO
from escolas.models import EscolaNaica
from frequencia.models import ChamadaGeral
from matriculas import regras as regras_matricula
from matriculas.models import Matricula
from oficinas.models import Designacao
from oficinas.tests import criar_tag
from oficinas.tests import criar_oficina

from . import grafico, indicadores
from .filtros import FiltrosAlunosForm, com_idade

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
        cls.danca = criar_oficina(criar_tag(escola=cls.alfa, nome='Arte'), 'Dança',
                                  dias_semana=[HOJE.weekday()], vagas=2, **periodo)
        cls.musica = criar_oficina(criar_tag(escola=cls.beta, nome='Som'), 'Música',
                                   dias_semana=[outro_dia], vagas=10, **periodo)
        cls.ana = criar_aluno(cls.alfa, 960000001, 'Ana')
        cls.bia = criar_aluno(cls.alfa, 960000002, 'Bia')
        cls.caio = criar_aluno(cls.alfa, 960000003, 'Caio')  # fila de espera (sem matrícula)
        cls.bruno = criar_aluno(cls.beta, 960000004, 'Bruno')
        for aluno in (cls.ana, cls.bia):
            Matricula.objects.create(aluno=aluno, oficina=cls.danca)
        Matricula.objects.create(aluno=cls.bruno, oficina=cls.musica)
        Matricula.objects.update(data_inscricao=HOJE - timedelta(days=50))

    def lancar(self, oficina, data, presencas):
        for aluno, valor in presencas.items():
            ChamadaGeral.objects.update_or_create(escola=oficina.escola, aluno=aluno, data=data,
                                                 defaults={'status_presenca': valor})

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
        self.assertEqual(dados['cronograma']['total'], 2)
        # A tabela lista TODAS as unidades (inclusive as 10 reais da migração), em ordem alfabética.
        por_nome = {u['escola'].nome: u for u in dados['unidades']}
        self.assertEqual(len(dados['unidades']), EscolaNaica.objects.count())
        alfa, beta = por_nome['Naica Alfa'], por_nome['Naica Beta']
        self.assertEqual((alfa['alunos'], alfa['oficinas']), (3, 1))
        self.assertEqual((beta['alunos'], beta['oficinas']), (1, 1))
        self.assertEqual(por_nome['Naica Tibery']['oficinas'], 0)  # sem oficinas

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
        self.assertEqual(dados['cronograma']['total'], 1)
        self.assertNotIn('unidades', dados)


class IndicadoresTests(BaseDashboardTestCase):
    def test_alunos_incompletos_pendencias_e_fila(self):
        dados = indicadores.alunos(indicadores.recorte_da_unidade(self.alfa))
        self.assertEqual(dados['classificacao_pendente'], 0)  # Caio
        self.assertEqual(dados['incompletos'], 3)  # helpers criam só a etapa 1
        self.assertEqual(dict(dados['pendencias'])['Responsável'], 3)

    def test_cronograma_nao_depende_de_matriculas(self):
        dados = indicadores.cronograma(indicadores.recorte_da_unidade(self.alfa))
        self.assertEqual(dados['total'], 1)
        self.assertEqual(dados['turmas_pendentes'], 0)
    def test_frequencia_30_dias_semanas_e_risco(self):
        for dias in (1, 8, 15):
            self.lancar(self.danca, HOJE - timedelta(days=dias), {self.ana: 'P', self.bia: 'F'})
        self.lancar(self.danca, HOJE - timedelta(days=22), {self.ana: 'J', self.bia: 'F'})
        dados = indicadores.frequencia(indicadores.recorte_da_unidade(self.alfa), HOJE)
        self.assertEqual(dados['percentual'], 50)  # 4 de 8 (J conta como presença)
        self.assertEqual(len(dados['semanas']), 8)
        self.assertEqual([m.nome for m in dados['risco']], ['Bia'])
        self.assertEqual(dados['risco'][0].percentual, 0)

    def test_chamada_pendente_por_unidade_inclui_aluno_sem_oficina(self):
        recorte = indicadores.recorte_da_unidade(self.alfa)
        hoje = indicadores.operacao_de_hoje(recorte, HOJE)
        self.assertEqual(hoje['chamada_pendente'][0]['pendentes'], 3)
        self.lancar(self.danca, HOJE, {self.ana: 'P', self.bia: 'P'})
        hoje = indicadores.operacao_de_hoje(recorte, HOJE)
        self.assertEqual(hoje['chamada_pendente'][0]['pendentes'], 1)
        self.lancar(self.danca, HOJE, {self.caio: 'P'})
        self.assertEqual(indicadores.operacao_de_hoje(recorte, HOJE)['chamada_pendente'], [])

    def test_frequencia_independe_de_oficinas_e_exclui_revisoes(self):
        ChamadaGeral.objects.create(escola=self.alfa, aluno=self.caio, data=HOJE, status_presenca='J')
        ChamadaGeral.objects.create(escola=self.alfa, aluno=self.ana, data=HOJE, status_presenca='')
        dados = indicadores.frequencia(indicadores.recorte_da_unidade(self.alfa), HOJE)
        self.assertEqual((dados['chamadas'], dados['percentual']), (1, 100))
        self.assertEqual(dados['revisoes'][0]['total'], 1)
        self.assertNotIn('sem_monitor', indicadores.operacao_de_hoje(indicadores.recorte_da_unidade(self.alfa), HOJE))
        self.client.force_login(self.coord_alfa)
        resposta = self.client.get(reverse('dashboard:painel'))
        self.assertContains(resposta, 'Presenças históricas aguardando revisão')
        self.assertNotContains(resposta, 'Sem monitor escalado')


class ChamadasPorTurnoTests(BaseDashboardTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Aluno.objects.filter(pk__in=[cls.caio.pk, cls.bruno.pk]).update(turno=Aluno.Turno.TARDE)

    def turnos(self, escola=None, filtros=None):
        recorte = indicadores.recorte_da_unidade(escola or self.alfa)
        if filtros is not None:
            recorte = filtros.filtrar_recorte(recorte, HOJE)
        operacao = indicadores.operacao_de_hoje(recorte, HOJE)
        return {item['turno']: item for item in operacao['chamadas_por_turno'][(escola or self.alfa).pk]}

    def test_concluir_manha_nao_conclui_tarde_e_falta_conta_como_chamada_feita(self):
        self.lancar(self.danca, HOJE, {self.ana: 'P', self.bia: 'J'})
        turnos = self.turnos()
        self.assertEqual(turnos['MANHA']['pendentes'], 0)
        self.assertEqual(turnos['TARDE']['pendentes'], 1)
        self.lancar(self.danca, HOJE, {self.caio: 'F'})
        self.assertEqual(self.turnos()['TARDE']['pendentes'], 0)

    def test_chamada_parcial_revisao_e_outro_dia_permanecem_pendentes(self):
        self.lancar(self.danca, HOJE, {self.ana: 'P', self.bia: ''})
        self.lancar(self.danca, HOJE - timedelta(days=1), {self.caio: 'P'})
        turnos = self.turnos()
        self.assertEqual(turnos['MANHA']['pendentes'], 1)
        self.assertEqual(turnos['TARDE']['pendentes'], 1)

    def test_turno_sem_alunos_nao_vira_chamada_feita(self):
        turnos = self.turnos(self.beta)
        self.assertEqual(turnos['MANHA']['total'], 0)
        self.assertEqual(turnos['MANHA']['pendentes'], 0)
        self.assertEqual(turnos['TARDE']['total'], 1)
        self.assertEqual(turnos['TARDE']['pendentes'], 1)

    def test_alunos_sem_turno_continuam_visiveis_separadamente(self):
        Aluno.objects.filter(pk=self.ana.pk).update(turno=None)
        Aluno.objects.filter(pk=self.bia.pk).update(turno='')
        self.lancar(self.danca, HOJE, {self.ana: 'F'})
        turnos = self.turnos()
        self.assertEqual((turnos['']['total'], turnos['']['pendentes']), (2, 1))
        self.assertEqual(turnos['MANHA']['total'], 0)
        self.assertEqual(turnos['TARDE']['pendentes'], 1)

    def test_filtros_de_alunos_tambem_recortam_os_status_por_turno(self):
        Aluno.objects.filter(pk__in=[self.bia.pk, self.caio.pk]).update(sexo='M')
        self.lancar(self.danca, HOJE, {self.ana: 'J'})
        filtros = FiltrosAlunosForm({'sexo': 'F'}, user=self.diretor)
        self.assertTrue(filtros.is_valid())
        turnos = self.turnos(filtros=filtros)
        self.assertEqual((turnos['MANHA']['total'], turnos['MANHA']['pendentes']), (1, 0))
        self.assertEqual(turnos['TARDE']['total'], 0)

    def test_chamada_historica_de_aluno_de_outra_unidade_nao_conclui_turno(self):
        Matricula.objects.create(aluno=self.bruno, oficina=self.danca)
        self.lancar(self.danca, HOJE, {self.bruno: 'P'})
        self.assertEqual(self.turnos()['TARDE']['pendentes'], 1)

    def test_tabela_mostra_manha_feita_e_tarde_pendente(self):
        self.lancar(self.danca, HOJE, {self.ana: 'P', self.bia: 'J'})
        self.client.force_login(self.diretor)
        resposta = self.client.get(reverse('dashboard:painel'))
        self.assertContains(resposta, '''<div class="chamada-turno">
            <span class="fw-semibold">Manhã</span>
            <span class="text-success"><i class="bi bi-check-circle" aria-hidden="true"></i> Chamada feita</span>
            </div>''', html=True)
        self.assertContains(resposta, '''<div class="chamada-turno">
            <span class="fw-semibold">Tarde</span>
            <span class="text-warning-emphasis" title="1 atendido sem chamada"><i class="bi bi-clock" aria-hidden="true"></i> Pendente</span>
            </div>''', html=True)


class PresencasSemanaisTests(BaseDashboardTestCase):
    hoje = date(2026, 11, 6)

    def test_bolinha_soma_presencas_e_justificativas_sem_contar_faltas_ou_revisoes(self):
        self.lancar(self.danca, self.hoje, {self.ana: 'P', self.bia: 'F', self.caio: ''})
        self.lancar(self.danca, self.hoje - timedelta(days=1), {self.ana: 'J', self.bia: 'J'})
        self.lancar(self.danca, self.hoje + timedelta(days=1), {self.ana: 'P'})
        self.lancar(self.danca, self.hoje - timedelta(days=7), {self.ana: 'F'})
        self.lancar(self.musica, self.hoje, {self.bruno: 'P'})
        dados = indicadores.frequencia(indicadores.recorte_da_unidade(self.alfa), self.hoje)
        self.assertEqual((dados['semanas'][-1]['presencas'], dados['semanas'][-1]['chamadas']), (3, 4))
        self.assertEqual(dados['semanas'][-1]['percentual'], 75)
        self.assertEqual(dados['semanas'][-2]['presencas'], 0)
        self.assertEqual(dados['semanas'][-2]['percentual'], 0)
        self.assertIsNone(dados['semanas'][-3]['percentual'])
        self.client.force_login(self.coord_alfa)
        with patch('dashboard.views.timezone.localdate', return_value=self.hoje):
            resposta = self.client.get(reverse('dashboard:painel'))
        self.assertRegex(resposta.content.decode(), r'class="ponto-quantidade"[^>]*>3</text>')
        self.assertRegex(resposta.content.decode(), r'class="ponto-quantidade"[^>]*>0</text>')
        self.assertContains(resposta, 'Presenças e justificativas: 3')
        self.assertContains(resposta, 'Registros de chamada: 4')

    def test_quantidade_semanal_respeita_filtros_de_alunos(self):
        Aluno.objects.filter(pk=self.bia.pk).update(sexo='M')
        self.lancar(self.danca, self.hoje, {self.ana: 'J', self.bia: 'P'})
        filtros = FiltrosAlunosForm({'sexo': 'F'}, user=self.coord_alfa)
        self.assertTrue(filtros.is_valid())
        dados = indicadores.painel(self.coord_alfa, filtros, self.hoje)
        self.assertEqual(dados['frequencia']['semanas'][-1]['presencas'], 1)


class FiltrosDashboardTests(BaseDashboardTestCase):
    hoje = date(2026, 11, 3)

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.duda = criar_aluno(cls.beta, 960000005, 'Duda')
        for aluno, nascimento, sexo in (
            (cls.ana, date(2010, 9, 10), 'F'),
            (cls.bia, date(2011, 11, 3), 'F'),
            (cls.caio, date(2010, 9, 20), 'M'),
            (cls.bruno, date(2009, 9, 1), 'M'),
            (cls.duda, date(2010, 9, 15), 'F'),
        ):
            Aluno.objects.filter(pk=aluno.pk).update(data_nascimento=nascimento, sexo=sexo)

    def consultar(self, params=None, user=None):
        self.client.force_login(user or self.diretor)
        with patch('dashboard.views.timezone.localdate', return_value=self.hoje):
            return self.client.get(reverse('dashboard:painel'), params or {})

    def nomes(self, response):
        return [a.nome for a in response.context['alunos_encontrados']]

    def test_idade_operadores_em_anos_completos(self):
        for operador, esperado in (
            ('gt', ['Ana', 'Bruno', 'Caio', 'Duda']),
            ('gte', ['Ana', 'Bia', 'Bruno', 'Caio', 'Duda']),
            ('eq', ['Bia']), ('lte', ['Bia']), ('lt', []),
        ):
            with self.subTest(operador=operador):
                response = self.consultar({'idade': 15, 'idade_operador': operador})
                self.assertEqual(self.nomes(response), esperado)

    def test_idade_considera_aniversario_hoje_ontem_e_amanha(self):
        for aluno, dia in ((self.ana, 2), (self.bia, 3), (self.caio, 4)):
            Aluno.objects.filter(pk=aluno.pk).update(data_nascimento=date(2010, 11, dia))
        idades = dict(com_idade(Aluno.objects.filter(escola=self.alfa), self.hoje).values_list('nome', 'idade'))
        self.assertEqual(idades, {'Ana': 16, 'Bia': 16, 'Caio': 15})

    def test_idade_em_nascimento_bissexto(self):
        Aluno.objects.filter(pk=self.ana.pk).update(data_nascimento=date(2012, 2, 29))
        qs = Aluno.objects.filter(pk=self.ana.pk)
        for hoje, esperado in ((date(2028, 2, 28), 15), (date(2028, 2, 29), 16),
                                (date(2027, 2, 28), 14), (date(2027, 3, 1), 15)):
            with self.subTest(hoje=hoje):
                self.assertEqual(com_idade(qs, hoje).get().idade, esperado)

    def test_idade_zero_e_um_filtro_ativo(self):
        Aluno.objects.filter(pk=self.ana.pk).update(data_nascimento=self.hoje)
        response = self.consultar({'idade': 0, 'idade_operador': 'eq'})
        self.assertTrue(response.context['filtros_ativos'])
        self.assertEqual(self.nomes(response), ['Ana'])

    def test_mes_aniversario_independe_do_ano(self):
        response = self.consultar({'mes_aniversario': 9})
        self.assertEqual(self.nomes(response), ['Ana', 'Bruno', 'Caio', 'Duda'])
        self.assertContains(response, '<option value="9" selected>Setembro</option>', html=True)

    def test_sexo(self):
        for sexo, esperado in (('M', ['Bruno', 'Caio']), ('F', ['Ana', 'Bia', 'Duda']), ('O', [])):
            with self.subTest(sexo=sexo):
                self.assertEqual(self.nomes(self.consultar({'sexo': sexo})), esperado)

    def test_combina_idade_mes_e_sexo_na_rede(self):
        response = self.consultar({'idade': 15, 'idade_operador': 'gt', 'mes_aniversario': 9, 'sexo': 'F'})
        self.assertEqual(self.nomes(response), ['Ana', 'Duda'])
        self.assertEqual(response.context['alunos']['total'], 2)
        self.assertEqual(response.context['alunos']['incompletos'], 2)
        self.assertEqual(response.context['alunos']['classificacao_pendente'], 0)
        unidades = {u['escola'].pk: u for u in response.context['unidades']}
        self.assertEqual(unidades[self.alfa.pk]['alunos'], 1)
        self.assertEqual(unidades[self.beta.pk]['alunos'], 1)

    def test_diretor_combina_unidade_com_os_outros_filtros(self):
        response = self.consultar({'escola': self.beta.pk, 'idade': 15, 'sexo': 'F', 'mes_aniversario': 9})
        self.assertEqual(self.nomes(response), ['Duda'])
        self.assertEqual(response.context['unidade_painel'], self.beta)
        self.assertNotIn('unidades', response.context)
        self.assertNotIn(CHAVE_SESSAO, self.client.session)  # filtro não muda a unidade em foco

    def test_coordenador_nao_amplia_escopo_com_parametro_ou_sessao(self):
        self.client.force_login(self.coord_alfa)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.beta.pk
        sessao.save()
        response = self.consultar({'escola': self.beta.pk, 'idade': 15, 'sexo': 'F'}, self.coord_alfa)
        self.assertEqual(self.nomes(response), ['Ana'])
        self.assertNotIn('escola', response.context['filtros'].fields)
        self.assertNotIn('unidades', response.context)
        self.assertEqual(response.context['cronograma']['total'], 1)

    def test_diretor_em_foco_nao_amplia_escopo_por_parametro(self):
        self.client.force_login(self.diretor)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.alfa.pk
        sessao.save()
        response = self.consultar({'escola': self.beta.pk, 'idade': 15, 'sexo': 'F'})
        self.assertEqual(self.nomes(response), ['Ana'])
        self.assertEqual(response.context['unidade_painel'], self.alfa)
        self.assertNotIn('escola', response.context['filtros'].fields)

    def test_aluno_matriculado_na_unidade_e_contado_uma_vez(self):

        self.danca.save()
        Matricula.objects.create(aluno=self.duda, oficina=self.danca)  # vínculo histórico entre unidades
        response = self.consultar({'idade': 15, 'sexo': 'F'}, self.coord_alfa)
        self.assertEqual(self.nomes(response), ['Ana', 'Duda'])

    def test_matriculas_frequencia_grafico_e_risco_seguem_filtros(self):


        self.danca.dias_semana = [self.hoje.weekday()]
        self.danca.save()
        for dias in (1, 8, 15):
            self.lancar(self.danca, self.hoje - timedelta(days=dias), {self.ana: 'P', self.bia: 'F'})
        filtros = FiltrosAlunosForm({'idade': 15, 'idade_operador': 'gt', 'sexo': 'F'}, user=self.coord_alfa)
        self.assertTrue(filtros.is_valid())
        dados = indicadores.painel(self.coord_alfa, filtros, self.hoje)
        self.assertEqual(dados['frequencia']['percentual'], 100)
        self.assertEqual(dados['frequencia']['chamadas'], 3)
        self.assertEqual(sum(s['chamadas'] for s in dados['frequencia']['semanas']), 3)
        self.assertEqual(dados['frequencia']['risco'], [])
        self.assertEqual([o.pk for o in dados['operacao']['oficinas']], [self.danca.pk])
        unidades = {u['escola'].pk: u for u in indicadores.por_unidade(self.hoje, filtros)}
        self.assertEqual(unidades[self.alfa.pk]['frequencia'], 100)

    def test_resultado_vazio(self):
        response = self.consultar({'idade': 100})
        self.assertEqual(response.context['alunos']['total'], 0)
        self.assertEqual(response.context['cronograma']['total'], 2)
        self.assertIsNone(response.context['frequencia']['percentual'])
        self.assertContains(response, 'Nenhum atendido encontrado com os filtros selecionados.')

    def test_filtros_invalidos_exibem_erros(self):
        for params in ({'idade': '-1'}, {'idade': 'abc'}, {'idade': '151'}, {'idade_operador': 'x'},
                       {'mes_aniversario': '13'}, {'sexo': 'X'}, {'escola': 'abc'}, {'escola': '99999999'}):
            with self.subTest(params=params):
                response = self.consultar(params)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context['filtros_validos'])
                self.assertContains(response, 'Revise os filtros indicados')
                self.assertNotIn('alunos', response.context)

    def test_paginacao_preserva_filtros(self):
        for i in range(26):
            aluno = criar_aluno(self.alfa, 960000100 + i, f'Atendida {i:02}')
            Aluno.objects.filter(pk=aluno.pk).update(data_nascimento=date(2010, 9, 1))
        response = self.consultar({'sexo': 'F', 'mes_aniversario': 9, 'page': 2})
        self.assertEqual(response.context['alunos_encontrados'].number, 2)
        self.assertEqual(response.context['alunos_encontrados'].paginator.count, 28)
        self.assertEqual(len(self.nomes(response)), 3)
        self.assertContains(response, 'sexo=F&amp;mes_aniversario=9&amp;page=1')
        self.assertContains(response, 'value="/dashboard/?sexo=F&amp;mes_aniversario=9"')

    def test_limpar_filtros_volta_aos_indicadores_do_escopo(self):
        self.consultar({'sexo': 'M'}, self.coord_alfa)
        response = self.consultar(user=self.coord_alfa)
        self.assertFalse(response.context['filtros_ativos'])
        self.assertEqual(response.context['alunos']['total'], 3)
        self.assertNotIn('alunos_encontrados', response.context)


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
        oficina = criar_oficina(criar_tag(escola=escola, nome='T'), 'Teatro',
                                data_inicio=HOJE - timedelta(days=60), data_fim=HOJE + timedelta(days=60))
        aluno = criar_aluno(escola, 970000001, 'Duda')
        Matricula.objects.create(aluno=aluno, oficina=oficina)
        Matricula.objects.update(data_inscricao=HOJE - timedelta(days=50))
        ChamadaGeral.objects.create(escola=escola, aluno=aluno, data=HOJE - timedelta(days=3), status_presenca='P')
        self.client.force_login(diretor)
        response = self.client.get(reverse('dashboard:painel'))
        self.assertContains(response, 'Frequência por semana')
        self.assertNotRegex(response.content.decode(), r'(cx|cy|x|y1|points)="\d+,\d+"')
