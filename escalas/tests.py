from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.tests import criar_usuario
from core.acesso import NivelAcesso
from escolas.foco import CHAVE_SESSAO
from escolas.models import EscolaNaica
from oficinas.models import AtividadeCronograma, Designacao, Oficina
from oficinas.tests import criar_oficina, criar_tag

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
        tipo_c = criar_tag(escola=cls.canaa, nome='Esporte')
        tipo_t = criar_tag(escola=cls.tibery, nome='Arte')
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


class CronogramaTests(BaseEscalaTestCase):
    def nomes(self, agenda):
        return {b['oficina'].nome for c in agenda['colunas'] for b in c['blocos']}

    def test_cronograma_independe_de_instrutores(self):
        self.capoeira.turmas = ['A', 'B']
        self.capoeira.save(update_fields=['turmas'])
        self.client.force_login(self.coord_canaa)
        resposta = self.client.get(reverse('escalas:grade'))
        self.assertContains(resposta, 'Cronograma das oficinas')
        self.assertContains(resposta, '<strong>Turma:</strong> A, B')
        self.assertNotContains(resposta, 'Montar escala')
        self.assertNotContains(resposta, 'sem monitor')
        self.assertNotContains(resposta, 'Fazer a chamada')
        self.assertFalse(Designacao.objects.exists())

    def test_filtros_por_turma_e_turno(self):
        self.capoeira.turmas = ['A', 'B']
        self.capoeira.save(update_fields=['turmas'])
        self.teatro.turmas = ['C']
        self.teatro.save(update_fields=['turmas'])
        self.assertEqual(self.nomes(regras.agenda_semanal(self.coord_canaa, turma='A', turno='MANHA')), {'Capoeira'})
        self.assertEqual(self.nomes(regras.agenda_semanal(self.coord_canaa, turma='C')), {'Teatro'})
        self.assertEqual(self.nomes(regras.agenda_semanal(self.coord_canaa, turma='A', turno='TARDE')), set())

    def test_escopo_coordenador_e_diretor_em_foco(self):
        self.assertEqual(self.nomes(regras.agenda_semanal(self.coord_canaa)), {'Capoeira', 'Teatro'})
        self.client.force_login(self.diretor)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.canaa.pk
        sessao.save()
        resposta = self.client.get(reverse('escalas:grade'), {'escola': self.tibery.pk, 'turno': 'MANHA'})
        self.assertEqual(self.nomes(resposta.context['agenda']), {'Capoeira', 'Teatro'})

    def test_instrutor_consulta_sem_chamadas_ou_alunos(self):
        Designacao.objects.create(oficina=self.capoeira, monitor=self.ana)
        self.client.force_login(self.ana)
        resposta = self.client.get(reverse('escalas:grade'))
        self.assertEqual(self.nomes(resposta.context['agenda']), {'Capoeira'})
        self.assertNotContains(resposta, 'Chamada geral')
        self.assertNotContains(resposta, 'Fazer a chamada')
        self.assertNotContains(resposta, 'Atendidos matriculados')
        self.assertRedirects(self.client.get(reverse('escalas:minha_semana')), reverse('escalas:grade'))

    def test_antiga_escala_nao_atribui_responsabilidades(self):
        self.client.force_login(self.coord_canaa)
        url = reverse('escalas:monitor', args=[self.ana.pk])
        self.assertRedirects(self.client.get(url), reverse('escalas:grade'))
        self.assertEqual(self.client.post(url, {f'atende_{self.capoeira.pk}': 'on'}).status_code, 405)
        self.assertFalse(Designacao.objects.exists())

    def test_sobreposicao_e_posicoes_em_porcentagem(self):
        agenda = regras.agenda_semanal(self.diretor)
        segunda = next(c for c in agenda['colunas'] if c['dia'] == 0)
        self.assertEqual([b['largura'] for b in segunda['blocos']], [50.0, 50.0])
        quarta = next(c for c in agenda['colunas'] if c['dia'] == 2)
        self.assertEqual((quarta['blocos'][0]['top'], quarta['blocos'][0]['altura']), (25.0, 50.0))
        self.client.force_login(self.diretor)
        resposta = self.client.get(reverse('escalas:grade'), {'escola': self.canaa.pk, 'turno': 'MANHA'})
        self.assertContains(resposta, 'width: 100.0%')
        self.assertNotRegex(resposta.content.decode(), r'(top|height|left|width): \d+,\d')

    def dados(self, oficina=None, **extra):
        return {'oficina': (oficina or self.capoeira.oficina).pk, 'turno': 'MANHA',
                'turmas': ['A', 'B'], 'dias_semana': ['1', '3'],
                'horario': '08:00', 'horario_fim': '10:00', **extra}

    def test_coordenador_vincula_catalogo_global_e_troca_oficina_a_qualquer_momento(self):
        nova = Oficina.objects.create(nome='Educação Física')
        self.client.force_login(self.coord_canaa)
        resposta = self.client.post(reverse('escalas:criar'), self.dados(escola=self.tibery.pk))
        self.assertRedirects(resposta, reverse('escalas:grade'))
        atividade = AtividadeCronograma.objects.latest('pk')
        self.assertEqual(atividade.escola, self.canaa)
        self.assertEqual(atividade.turmas, ['A', 'B'])
        resposta = self.client.post(reverse('escalas:editar', args=[atividade.pk]), self.dados(nova))
        self.assertRedirects(resposta, reverse('escalas:detalhe', args=[atividade.pk]))
        atividade.refresh_from_db()
        self.assertEqual(atividade.nome, 'Educação Física')
        self.assertFalse(Designacao.objects.exists())
        from frequencia.models import ChamadaGeral
        self.assertFalse(ChamadaGeral.objects.exists())

    def test_formulario_so_tem_oficina_turmas_e_horario(self):
        self.client.force_login(self.coord_canaa)
        resposta = self.client.get(reverse('escalas:criar'))
        campos = set(resposta.context['form'].fields)
        self.assertEqual(campos, {'oficina', 'instrutor_nome', 'turmas', 'turno', 'dias_semana', 'horario', 'horario_fim'})
        for campo in ('data_inicio', 'data_fim', 'carga_horaria', 'nome_monitor'):
            self.assertNotContains(resposta, f'name="{campo}"')

    def test_diretor_escolhe_unidade_e_foco_restringe_edicao(self):
        self.client.force_login(self.diretor)
        resposta = self.client.post(reverse('escalas:criar'), self.dados(escola=self.tibery.pk))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(AtividadeCronograma.objects.latest('pk').escola, self.tibery)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.canaa.pk
        sessao.save()
        for nome in ('editar', 'excluir'):
            self.assertEqual(self.client.post(reverse(f'escalas:{nome}', args=[self.danca.pk]), self.dados()).status_code, 404)

    def test_coordenador_nao_edita_nem_remove_cronograma_de_outra_unidade(self):
        self.client.force_login(self.coord_canaa)
        for nome in ('editar', 'excluir'):
            self.assertEqual(self.client.post(reverse(f'escalas:{nome}', args=[self.danca.pk]), self.dados()).status_code, 404)

    def test_instrutor_consulta_e_nao_edita_cronograma(self):
        self.client.force_login(self.ana)
        for nome, args in (('criar', []), ('editar', [self.capoeira.pk]), ('excluir', [self.capoeira.pk])):
            self.assertEqual(self.client.post(reverse(f'escalas:{nome}', args=args), self.dados()).status_code, 403)

    def test_oficina_arquivada_nao_pode_ser_atribuida_a_novo_horario(self):
        self.capoeira.oficina.arquivada = True
        self.capoeira.oficina.save()
        self.client.force_login(self.coord_canaa)
        total = AtividadeCronograma.objects.count()
        resposta = self.client.post(reverse('escalas:criar'), self.dados())
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('oficina', resposta.context['form'].errors)
        self.assertEqual(AtividadeCronograma.objects.count(), total)

    def test_turmas_dias_e_horarios_sao_validados(self):
        self.client.force_login(self.coord_canaa)
        for dados, campo in ((self.dados(turmas=[]), 'turmas'), (self.dados(turmas=['D']), 'turmas'),
                             (self.dados(dias_semana=[]), 'dias_semana'), (self.dados(horario_fim='07:00'), 'horario_fim')):
            resposta = self.client.post(reverse('escalas:criar'), dados)
            self.assertIn(campo, resposta.context['form'].errors)

    def test_remover_horario_com_historico_preserva_matricula(self):
        from alunos.tests import criar_aluno
        from matriculas.models import Matricula
        aluno = criar_aluno(self.canaa, 944000001)
        Matricula.objects.create(aluno=aluno, oficina=self.capoeira)
        self.client.force_login(self.coord_canaa)
        self.assertEqual(self.client.post(reverse('escalas:excluir', args=[self.capoeira.pk])).status_code, 302)
        self.capoeira.refresh_from_db()
        self.assertFalse(self.capoeira.ativo)
        self.assertEqual(Matricula.objects.count(), 1)
        self.assertNotIn('Capoeira', self.nomes(regras.agenda_semanal(self.coord_canaa)))

    def test_instrutor_opcional_e_exibido_sem_criar_designacoes(self):
        self.client.force_login(self.coord_canaa)
        resposta = self.client.post(reverse('escalas:criar'), self.dados(instrutor_nome='João da Silva'))
        self.assertEqual(resposta.status_code, 302)
        atividade = AtividadeCronograma.objects.latest('pk')
        self.assertEqual(atividade.instrutor_nome, 'João da Silva')
        self.assertFalse(Designacao.objects.exists())
        ficha = self.client.get(reverse('escalas:detalhe', args=[atividade.pk]))
        self.assertContains(ficha, 'João da Silva')
        grade = self.client.get(reverse('escalas:grade'))
        self.assertContains(grade, '<strong>Instrutor:</strong> João da Silva')
        self.assertContains(grade, '<strong>Turma:</strong> A, B')
        self.assertContains(grade, '<strong>Horário:</strong> 08:00–10:00')
        self.assertNotContains(grade, 'agenda-bloco-monitores')
        self.assertNotContains(grade, 'Manhã · Turma')

    def test_card_mostra_instrutor_nao_informado_e_escapa_texto_cadastrado(self):
        self.client.force_login(self.coord_canaa)
        grade = self.client.get(reverse('escalas:grade'))
        self.assertContains(grade, '<strong>Instrutor:</strong> Não informado')
        self.capoeira.instrutor_nome = '<script>alert("instrutor")</script>'
        self.capoeira.save(update_fields=['instrutor_nome'])
        grade = self.client.get(reverse('escalas:grade'))
        self.assertNotContains(grade, self.capoeira.instrutor_nome)
        self.assertContains(grade, '&lt;script&gt;')

    def test_cards_curtos_e_simultaneos_tem_espaco_sem_alterar_horarios(self):
        curta = AtividadeCronograma.objects.create(
            escola=self.canaa, oficina=self.teatro.oficina, turno='MANHA', turmas=['A'],
            dias_semana=[0], horario=time(9), horario_fim=time(9, 15),
        )
        agenda = regras.agenda_semanal(self.diretor, escola=self.canaa)
        segunda = next(coluna for coluna in agenda['colunas'] if coluna['dia'] == 0)
        for bloco in segunda['blocos']:
            altura_rem = agenda['altura_hora'] * agenda['total_horas'] * bloco['altura'] / 100
            largura_rem = segunda['largura_minima'] * bloco['largura'] / 100
            self.assertGreaterEqual(altura_rem, 7.49)
            self.assertGreaterEqual(largura_rem, 13)
        bloco_curto = next(b for b in segunda['blocos'] if b['oficina'].pk == curta.pk)
        self.assertEqual(bloco_curto['inicio'], 9 * 60)
        self.assertEqual(bloco_curto['fim'], 9 * 60 + 15)
        self.assertEqual(bloco_curto['largura'], 50)


class CronogramaDiretorTests(BaseEscalaTestCase):
    def consultar(self, params=None):
        self.client.force_login(self.diretor)
        return self.client.get(reverse('escalas:grade'), params or {})

    def atividades(self, agenda):
        return {bloco['oficina'].pk for coluna in agenda['colunas'] for bloco in coluna['blocos']}

    def test_abertura_pede_naica_e_turno_sem_exibir_cronograma_da_rede(self):
        resposta = self.consultar()
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.context['agenda'])
        self.assertContains(resposta, 'name="escola"')
        self.assertContains(resposta, 'name="turno"')
        self.assertNotContains(resposta, 'name="turma"')
        self.assertContains(resposta, 'Selecione o Naica e o turno')
        self.assertNotContains(resposta, 'agenda-bloco')
        self.assertFalse(resposta.context['filtros_diretor'].is_bound)

    def test_filtra_naica_e_turno_e_reune_todas_as_turmas_da_semana(self):
        self.capoeira.turmas = ['A', 'B']
        self.capoeira.save(update_fields=['turmas'])
        self.teatro.turmas = ['C']
        self.teatro.save(update_fields=['turmas'])
        resposta = self.consultar({'escola': self.canaa.pk, 'turno': 'MANHA', 'turma': 'A'})
        self.assertEqual(self.atividades(resposta.context['agenda']), {self.capoeira.pk, self.teatro.pk})
        self.assertEqual(resposta.context['unidade_cronograma'], self.canaa)
        self.assertContains(resposta, '<strong>Turma:</strong> A, B')
        self.assertContains(resposta, '<strong>Turma:</strong> C')
        self.assertEqual(resposta.context['filtros_diretor']['escola'].value(), str(self.canaa.pk))
        self.assertEqual(resposta.context['filtros_diretor']['turno'].value(), 'MANHA')
        self.assertNotIn(CHAVE_SESSAO, self.client.session)
        dias = {coluna['dia'] for coluna in resposta.context['agenda']['colunas'] if coluna['blocos']}
        self.assertEqual(dias, {0, 1, 2, 3, 4})

    def test_turno_selecionado_inclui_fim_de_semana_quando_houver_oficina(self):
        tarde = AtividadeCronograma.objects.create(
            escola=self.canaa, oficina=self.capoeira.oficina, turno='TARDE', turmas=['C'],
            dias_semana=[1, 5, 6], horario=time(14), horario_fim=time(16),
        )
        resposta = self.consultar({'escola': self.canaa.pk, 'turno': 'TARDE'})
        self.assertEqual(self.atividades(resposta.context['agenda']), {tarde.pk})
        dias = {coluna['dia'] for coluna in resposta.context['agenda']['colunas'] if coluna['blocos']}
        self.assertEqual(dias, {1, 5, 6})
        self.assertEqual(resposta.context['agenda']['horas'][0], 13)

    def test_trocar_naica_muda_somente_o_filtro_da_pagina(self):
        resposta = self.consultar({'escola': self.tibery.pk, 'turno': 'MANHA'})
        self.assertEqual(self.atividades(resposta.context['agenda']), {self.danca.pk})
        self.assertEqual(resposta.context['unidade_cronograma'], self.tibery)
        self.assertNotIn(CHAVE_SESSAO, self.client.session)

    def test_filtros_incompletos_ou_invalidos_nao_mostram_a_rede(self):
        for params, campo in (
            ({'turno': 'MANHA'}, 'escola'),
            ({'escola': self.canaa.pk}, 'turno'),
            ({'escola': 'invalida', 'turno': 'MANHA'}, 'escola'),
            ({'escola': 99999999, 'turno': 'MANHA'}, 'escola'),
            ({'escola': self.canaa.pk, 'turno': 'INVALIDO'}, 'turno'),
        ):
            with self.subTest(params=params):
                resposta = self.consultar(params)
                self.assertEqual(resposta.status_code, 200)
                self.assertIsNone(resposta.context['agenda'])
                self.assertIn(campo, resposta.context['filtros_diretor'].errors)
                self.assertNotContains(resposta, 'agenda-bloco')

    def test_recorte_vazio_exibe_aviso_sem_oficinas_de_outra_unidade(self):
        resposta = self.consultar({'escola': self.tibery.pk, 'turno': 'TARDE'})
        self.assertTrue(resposta.context['agenda']['vazia'])
        self.assertContains(resposta, 'Nenhuma oficina no cronograma para os filtros selecionados.')
        self.assertNotContains(resposta, 'agenda-bloco')

    def test_oficinas_arquivadas_e_horarios_inativos_ficam_fora(self):
        self.capoeira.ativo = False
        self.capoeira.save(update_fields=['ativo'])
        self.teatro.oficina.arquivada = True
        self.teatro.oficina.save(update_fields=['arquivada'])
        resposta = self.consultar({'escola': self.canaa.pk, 'turno': 'MANHA'})
        self.assertTrue(resposta.context['agenda']['vazia'])

    def test_unidade_em_foco_prevalece_e_nao_muda_com_o_filtro(self):
        self.client.force_login(self.diretor)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.canaa.pk
        sessao.save()
        resposta = self.client.get(reverse('escalas:grade'), {'escola': self.tibery.pk, 'turno': 'MANHA'})
        self.assertEqual(self.atividades(resposta.context['agenda']), {self.capoeira.pk, self.teatro.pk})
        self.assertEqual(list(resposta.context['filtros_diretor'].fields['escola'].queryset), [self.canaa])
        self.assertEqual(resposta.context['filtros_diretor']['escola'].value(), str(self.canaa.pk))
        self.assertEqual(self.client.session[CHAVE_SESSAO], self.canaa.pk)

    def test_coordenador_mantem_filtros_de_turma_turno_e_escopo_da_unidade(self):
        self.teatro.turmas = ['C']
        self.teatro.save(update_fields=['turmas'])
        self.client.force_login(self.coord_canaa)
        resposta = self.client.get(reverse('escalas:grade'), {
            'escola': self.tibery.pk, 'turno': 'MANHA', 'turma': 'C',
        })
        self.assertEqual(self.atividades(resposta.context['agenda']), {self.teatro.pk})
        self.assertContains(resposta, 'name="turma"')
        self.assertNotContains(resposta, 'name="escola"')
        self.assertFalse(regras.agenda_semanal(self.coord_canaa, escola=self.tibery)['colunas'][0]['blocos'])
