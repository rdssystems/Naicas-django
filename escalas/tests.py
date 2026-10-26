from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.tests import criar_usuario
from core.acesso import NivelAcesso
from escolas.foco import CHAVE_SESSAO
from escolas.models import EscolaNaica
from oficinas.models import Designacao, Oficina, TipoOficina
from oficinas.tests import criar_oficina

from . import regras

HOJE = timezone.localdate()


class BaseEscalaTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.canaa = EscolaNaica.objects.create(nome='Naica Alfa')
        cls.tibery = EscolaNaica.objects.create(nome='Naica Beta')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord_canaa = criar_usuario('coord_canaa', NivelAcesso.COORDENADOR, cls.canaa)
        cls.ana = criar_usuario('ana', NivelAcesso.MONITOR)
        cls.bruno = criar_usuario('bruno', NivelAcesso.MONITOR)
        periodo = {'data_inicio': HOJE - timedelta(days=30), 'data_fim': HOJE + timedelta(days=60)}
        tipo_c = TipoOficina.objects.create(escola=cls.canaa, nome='Esporte')
        tipo_t = TipoOficina.objects.create(escola=cls.tibery, nome='Arte')
        # Capoeira seg/qua/sex 8-10 (Alfa); Dança seg 9-11 (Beta, choca na segunda); Teatro ter/qui 8-10 (Alfa).
        cls.capoeira = criar_oficina(tipo_c, 'Capoeira', dias_semana=[0, 2, 4], horario=time(8), horario_fim=time(10), **periodo)
        cls.danca = criar_oficina(tipo_t, 'Dança', dias_semana=[0], horario=time(9), horario_fim=time(11), **periodo)
        cls.teatro = criar_oficina(tipo_c, 'Teatro', dias_semana=[1, 3], horario=time(8), horario_fim=time(10), **periodo)

    def montar(self, user, monitor, escolhas):
        self.client.force_login(user)
        dados = {}
        for oficina, dias in escolhas.items():
            dados[f'atende_{oficina.pk}'] = 'on'
            dados[f'dias_{oficina.pk}'] = [str(d) for d in dias]
        return self.client.post(reverse('escalas:monitor', args=[monitor.pk]), dados)


class RegrasTests(BaseEscalaTestCase):
    def test_divide_oficina_por_dia_e_todos_os_dias_vira_vazio(self):
        regras.salvar_escala(self.ana, self.diretor, {self.capoeira.pk: [0, 2]})
        regras.salvar_escala(self.bruno, self.diretor, {self.capoeira.pk: [0, 2, 4]})
        ana = Designacao.objects.get(monitor=self.ana)
        bruno = Designacao.objects.get(monitor=self.bruno)
        self.assertEqual((ana.dias_semana, ana.dias_display), ([0, 2], 'Seg, Qua'))
        self.assertEqual((bruno.dias_semana, bruno.todos_os_dias), ([], True))

    def test_choque_de_horario_e_recusado_mesmo_em_outra_unidade(self):
        regras.salvar_escala(self.ana, self.diretor, {self.danca.pk: [0]})
        with self.assertRaisesMessage(regras.EscalaRecusada, 'Choque de horário'):
            regras.salvar_escala(self.ana, self.coord_canaa, {self.capoeira.pk: [0, 2, 4]})
        # Sem a segunda-feira não há choque.
        regras.salvar_escala(self.ana, self.coord_canaa, {self.capoeira.pk: [2, 4]})
        self.assertEqual(Designacao.objects.filter(monitor=self.ana).count(), 2)

    def test_coordenador_so_mexe_na_propria_unidade_e_preserva_as_outras(self):
        regras.salvar_escala(self.ana, self.diretor, {self.danca.pk: [0]})
        with self.assertRaisesMessage(regras.EscalaRecusada, 'não pode montar escala'):
            regras.salvar_escala(self.ana, self.coord_canaa, {self.danca.pk: [0]})
        regras.salvar_escala(self.ana, self.coord_canaa, {self.teatro.pk: [1]})
        regras.salvar_escala(self.ana, self.coord_canaa, {})  # limpa só a unidade dele
        self.assertEqual(list(Designacao.objects.filter(monitor=self.ana).values_list('oficina__nome', flat=True)), ['Dança'])

    def test_dia_que_a_oficina_nao_tem_ou_nenhum_dia(self):
        with self.assertRaises(regras.EscalaRecusada):
            regras.salvar_escala(self.ana, self.diretor, {self.capoeira.pk: [1]})  # capoeira não tem terça
        with self.assertRaisesMessage(regras.EscalaRecusada, 'pelo menos um dia'):
            regras.salvar_escala(self.ana, self.diretor, {self.capoeira.pk: []})

    def test_so_monitor_ativo(self):
        with self.assertRaises(regras.EscalaRecusada):
            regras.salvar_escala(self.coord_canaa, self.diretor, {self.capoeira.pk: [0]})
        self.bruno.is_active = False
        self.bruno.save()
        with self.assertRaises(regras.EscalaRecusada):
            regras.salvar_escala(self.bruno, self.diretor, {self.capoeira.pk: [0]})

    def test_oficina_encerrada_sai_da_escala_mas_designacao_fica(self):
        regras.salvar_escala(self.ana, self.diretor, {self.teatro.pk: [1, 3]})
        Oficina.objects.filter(pk=self.teatro.pk).update(status=Oficina.Status.CONCLUIDO)
        regras.salvar_escala(self.ana, self.diretor, {self.capoeira.pk: [0]})
        self.assertTrue(Designacao.objects.filter(monitor=self.ana, oficina=self.teatro).exists())  # histórico
        linhas, _ = regras.grade_semanal(self.diretor)
        nomes = {i['designacao'].oficina.nome for linha in linhas for c in linha['celulas'] for i in c}
        self.assertEqual(nomes, {'Capoeira'})


class TelasTests(BaseEscalaTestCase):
    def test_montar_pela_tela_e_ver_na_grade(self):
        response = self.montar(self.coord_canaa, self.ana, {self.capoeira: [0, 2]})
        self.assertRedirects(response, reverse('escalas:grade'))
        grade = self.client.get(reverse('escalas:grade'), {'vista': 'monitores'})
        self.assertContains(grade, 'Capoeira')
        self.assertEqual([linha['monitor'] for linha in grade.context['linhas']], [self.ana])

    def test_choque_volta_para_a_tela_com_mensagem_e_nada_salvo(self):
        Designacao.objects.create(oficina=self.danca, monitor=self.ana)
        response = self.montar(self.coord_canaa, self.ana, {self.capoeira: [0]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choque de horário')
        self.assertContains(response, 'Também atende em outras unidades')  # Dança (Beta) só consulta
        self.assertFalse(Designacao.objects.filter(monitor=self.ana, oficina=self.capoeira).exists())

    def test_grade_respeita_unidade_do_coordenador_e_foco_do_diretor(self):
        Designacao.objects.create(oficina=self.capoeira, monitor=self.ana)
        Designacao.objects.create(oficina=self.danca, monitor=self.bruno)
        por_monitor = {'vista': 'monitores'}
        self.client.force_login(self.coord_canaa)
        self.assertEqual([l['monitor'] for l in self.client.get(reverse('escalas:grade'), por_monitor).context['linhas']], [self.ana])
        self.client.force_login(self.diretor)
        self.assertEqual(len(self.client.get(reverse('escalas:grade'), por_monitor).context['linhas']), 2)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.tibery.pk
        sessao.save()
        self.assertEqual([l['monitor'] for l in self.client.get(reverse('escalas:grade'), por_monitor).context['linhas']], [self.bruno])

    def test_permissoes(self):
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(reverse('escalas:grade')).status_code, 403)
        self.assertEqual(self.client.get(reverse('escalas:monitor', args=[self.bruno.pk])).status_code, 403)
        self.client.force_login(self.diretor)
        self.assertEqual(self.client.get(reverse('escalas:minha_semana')).status_code, 403)
        # Escala só de monitor ativo.
        self.assertEqual(self.client.get(reverse('escalas:monitor', args=[self.coord_canaa.pk])).status_code, 404)

    def test_minha_semana_com_chamada_de_hoje(self):
        Designacao.objects.create(oficina=self.capoeira, monitor=self.ana, dias_semana=[HOJE.weekday()]
                                  if HOJE.weekday() in (0, 2, 4) else [])
        self.client.force_login(self.ana)
        response = self.client.get(reverse('escalas:minha_semana'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Capoeira')
        if HOJE.weekday() in (0, 2, 4):
            self.assertContains(response, 'Fazer a chamada de hoje')

    def test_escala_so_orienta_monitor_lanca_chamada_em_qualquer_dia(self):
        Designacao.objects.create(oficina=self.capoeira, monitor=self.ana, dias_semana=[0])
        self.client.force_login(self.ana)
        response = self.client.get(reverse('frequencia:oficina', args=[self.capoeira.pk]))
        self.assertEqual(response.status_code, 200)


class AgendaTests(BaseEscalaTestCase):
    def coluna(self, agenda, dia):
        return next(c for c in agenda['colunas'] if c['dia'] == dia)

    def test_oficinas_sobrepostas_ficam_lado_a_lado(self):
        # Segunda (visão geral): Capoeira 8-10 (Alfa) e Dança 9-11 (Beta) se sobrepõem.
        segunda = self.coluna(regras.agenda_semanal(self.diretor), 0)
        blocos = {b['oficina'].nome: b for b in segunda['blocos']}
        self.assertEqual((blocos['Capoeira']['largura'], blocos['Dança']['largura']), (50.0, 50.0))
        self.assertEqual({blocos['Capoeira']['esquerda'], blocos['Dança']['esquerda']}, {0.0, 50.0})
        # Quarta só tem Capoeira: largura inteira.
        quarta = self.coluna(regras.agenda_semanal(self.diretor), 2)
        self.assertEqual([b['largura'] for b in quarta['blocos']], [100.0])

    def test_posicao_vertical_pelo_horario(self):
        agenda = regras.agenda_semanal(self.diretor)
        self.assertEqual((agenda['horas'][0], agenda['total_horas']), (7, 4))  # 7h às 11h
        capoeira = self.coluna(agenda, 2)['blocos'][0]
        self.assertEqual((capoeira['top'], capoeira['altura']), (25.0, 50.0))  # 8h-10h numa janela 7h-11h

    def test_sem_monitor_e_filtro_por_monitor(self):
        Designacao.objects.create(oficina=self.capoeira, monitor=self.ana, dias_semana=[0, 2])
        agenda = regras.agenda_semanal(self.diretor)
        sexta = self.coluna(agenda, 4)['blocos'][0]
        segunda = next(b for b in self.coluna(agenda, 0)['blocos'] if b['oficina'] == self.capoeira)
        self.assertTrue(sexta['sem_monitor'])
        self.assertEqual(segunda['monitores'], [self.ana])
        da_ana = regras.agenda_semanal(self.diretor, monitor=self.ana)
        dias_com_bloco = [c['dia'] for c in da_ana['colunas'] if c['blocos']]
        self.assertEqual(dias_com_bloco, [0, 2])

    def test_coordenador_ve_so_a_unidade(self):
        agenda = regras.agenda_semanal(self.coord_canaa)
        nomes = {b['oficina'].nome for c in agenda['colunas'] for b in c['blocos']}
        self.assertEqual(nomes, {'Capoeira', 'Teatro'})

    def test_abas_e_css_com_ponto_decimal(self):
        self.client.force_login(self.diretor)
        agenda = self.client.get(reverse('escalas:grade'))
        self.assertEqual(agenda.context['vista'], 'agenda')
        self.assertContains(agenda, 'width: 50.0%')
        self.assertNotRegex(agenda.content.decode(), r'(top|height|left|width): \d+,\d')
        por_monitor = self.client.get(reverse('escalas:grade'), {'vista': 'monitores'})
        self.assertEqual(por_monitor.context['vista'], 'monitores')
        filtrada = self.client.get(reverse('escalas:grade'), {'monitor': self.ana.pk})
        self.assertEqual(filtrada.context['monitor_filtro'], self.ana)
        self.assertContains(filtrada, 'ainda não tem oficinas na escala')
