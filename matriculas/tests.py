from datetime import date, time
from types import SimpleNamespace

from django.test import TestCase
from django.urls import reverse

from alunos.models import Aluno, FichaSaude
from alunos.tests import criar_aluno, criar_usuario, formatar
from core.acesso import NivelAcesso
from escolas.models import EscolaNaica
from oficinas.models import Oficina, TipoOficina
from oficinas.tests import criar_oficina

from . import regras
from .models import Matricula


def janela(dias, inicio, fim, data_inicio=date(2026, 3, 1), data_fim=date(2026, 6, 30)):
    return SimpleNamespace(
        dias_semana=dias, horario=time(*inicio), horario_fim=time(*fim), data_inicio=data_inicio, data_fim=data_fim,
    )


class ChoqueDeHorarioTests(TestCase):
    def test_regras_de_choque(self):
        seg_8_10 = janela([0], (8,), (10,))
        casos = [
            (janela([0, 2], (9,), (11,)), True),       # mesmo dia, horário sobreposto
            (janela([0], (10,), (12,)), False),        # encosta às 10h: não choca
            (janela([1, 3], (8,), (10,)), False),      # dias diferentes
            (janela([0], (8,), (10,), date(2026, 7, 1), date(2026, 12, 1)), False),  # períodos diferentes
            (janela([0], (7,), (12,)), True),          # contém
        ]
        for outra, esperado in casos:
            self.assertEqual(regras.horarios_se_chocam(seg_8_10, outra), esperado, outra)
            self.assertEqual(regras.horarios_se_chocam(outra, seg_8_10), esperado, outra)


class BaseMatriculasTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.escola_a = EscolaNaica.objects.create(nome='Naica Centro')
        cls.escola_b = EscolaNaica.objects.create(nome='Naica Norte')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord_a = criar_usuario('coord_a', NivelAcesso.COORDENADOR, cls.escola_a)
        cls.coord_b = criar_usuario('coord_b', NivelAcesso.COORDENADOR, cls.escola_b)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.outro_monitor = criar_usuario('outro_monitor', NivelAcesso.MONITOR)
        tipo_a = TipoOficina.objects.create(escola=cls.escola_a, nome='Dança')
        tipo_b = TipoOficina.objects.create(escola=cls.escola_b, nome='Música')
        # Seg/Qua 8-10 na A; Seg 9-11 na B (choca); Ter/Qui 8-10 na A (não choca).
        cls.danca = criar_oficina(tipo_a, 'Dança', dias_semana=[0, 2], horario=time(8), horario_fim=time(10), vagas=2)
        cls.violao = criar_oficina(tipo_b, 'Violão', dias_semana=[0], horario=time(9), horario_fim=time(11))
        cls.teatro = criar_oficina(tipo_a, 'Teatro', dias_semana=[1, 3], horario=time(8), horario_fim=time(10))
        cls.danca.monitores.add(cls.monitor)
        cls.ana = criar_aluno(cls.escola_a, 800000001, 'Ana')
        cls.bia = criar_aluno(cls.escola_a, 800000002, 'Bia')
        cls.caio = criar_aluno(cls.escola_a, 800000003, 'Caio')
        cls.bruno = criar_aluno(cls.escola_b, 800000004, 'Bruno')


class RegrasDeMatriculaTests(BaseMatriculasTestCase):
    def test_matricula_copia_unidade_e_turno_da_oficina(self):
        m = regras.matricular(self.ana, self.danca, self.coord_a)
        self.assertEqual((m.escola, m.turno, m.status), (self.escola_a, self.danca.turno, 'CURSANDO'))
        self.assertEqual(m.matriculado_por, self.coord_a)

    def test_aluno_com_cadastro_incompleto_pode_ser_matriculado(self):
        self.assertFalse(Aluno.objects.get(pk=self.ana.pk).cadastro_completo)
        regras.matricular(self.ana, self.danca, self.coord_a)

    def test_respeita_limite_de_vagas(self):
        regras.matricular(self.ana, self.danca, self.coord_a)
        regras.matricular(self.bia, self.danca, self.coord_a)
        with self.assertRaisesMessage(regras.MatriculaRecusada, 'sem vagas'):
            regras.matricular(self.caio, self.danca, self.coord_a)

    def test_desistencia_libera_vaga(self):
        m = regras.matricular(self.ana, self.danca, self.coord_a)
        regras.matricular(self.bia, self.danca, self.coord_a)
        regras.registrar_desistencia(m, self.coord_a, date(2026, 4, 1))
        regras.matricular(self.caio, self.danca, self.coord_a)
        m.refresh_from_db()
        self.assertEqual((m.status, m.data_desistencia), ('DESISTENTE', date(2026, 4, 1)))

    def test_varias_oficinas_sem_choque_e_recusa_com_choque(self):
        regras.matricular(self.ana, self.danca, self.coord_a)
        regras.matricular(self.ana, self.teatro, self.coord_a)  # Ter/Qui: ok
        # Violão (unidade B) choca na segunda com Dança.
        with self.assertRaisesMessage(regras.MatriculaRecusada, 'Choque de horário com "Dança"'):
            regras.matricular(self.ana, self.violao, self.diretor)

    def test_choque_so_conta_matricula_em_curso(self):
        m = regras.matricular(self.ana, self.danca, self.coord_a)
        regras.concluir(m, self.coord_a)
        regras.matricular(self.ana, self.violao, self.diretor)

    def test_nao_duplica_na_mesma_oficina_mas_permite_voltar(self):
        m = regras.matricular(self.ana, self.danca, self.coord_a)
        with self.assertRaisesMessage(regras.MatriculaRecusada, 'já está cursando'):
            regras.matricular(self.ana, self.danca, self.coord_a)
        regras.registrar_desistencia(m, self.coord_a)
        regras.matricular(self.ana, self.danca, self.coord_a)
        self.assertEqual(Matricula.objects.filter(aluno=self.ana, oficina=self.danca).count(), 2)

    def test_oficina_fechada_nao_aceita(self):
        Oficina.objects.filter(pk=self.teatro.pk).update(status=Oficina.Status.CONCLUIDO)
        self.teatro.refresh_from_db()
        with self.assertRaisesMessage(regras.MatriculaRecusada, 'não aceita matrículas'):
            regras.matricular(self.ana, self.teatro, self.coord_a)

    def test_coordenador_so_matricula_na_propria_unidade(self):
        with self.assertRaises(regras.MatriculaRecusada):
            regras.matricular(self.ana, self.violao, self.coord_a)
        with self.assertRaises(regras.MatriculaRecusada):
            regras.matricular(self.ana, self.danca, self.monitor)

    def test_so_encerra_matricula_em_curso(self):
        m = regras.matricular(self.ana, self.danca, self.coord_a)
        regras.concluir(m, self.coord_a, date(2026, 6, 30))
        with self.assertRaises(regras.MatriculaRecusada):
            regras.registrar_desistencia(m, self.coord_a)
        self.assertEqual(Matricula.objects.get(pk=m.pk).data_conclusao, date(2026, 6, 30))


class VisibilidadeTests(BaseMatriculasTestCase):
    def test_coordenador_passa_a_ver_aluno_de_outra_unidade_matriculado(self):
        self.assertFalse(Aluno.objects.visiveis_para(self.coord_b).filter(pk=self.ana.pk).exists())
        regras.matricular(self.ana, self.violao, self.coord_b)
        visiveis = Aluno.objects.visiveis_para(self.coord_b)
        self.assertEqual(set(visiveis), {self.ana, self.bruno})
        self.assertEqual(visiveis.filter(pk=self.ana.pk).count(), 1)  # sem duplicar pelo JOIN

    def test_etapa_6_nao_conta_para_o_selo(self):
        aluno = Aluno.objects.get(pk=self.ana.pk)
        self.assertFalse(aluno.etapas()[5][3])
        regras.matricular(self.ana, self.danca, self.coord_a)
        self.assertTrue(Aluno.objects.get(pk=self.ana.pk).etapas()[5][3])


class TelaMatricularNaOficinaTests(BaseMatriculasTestCase):
    def url(self, oficina):
        return reverse('matriculas:matricular_na_oficina', args=[oficina.pk])

    def test_busca_por_nome_so_ve_alunos_visiveis(self):
        self.client.force_login(self.coord_b)
        response = self.client.get(self.url(self.violao), {'q': 'B'})  # Bia (unidade A) e Bruno (B)
        nomes = {r['aluno'].nome for r in response.context['resultados']}
        self.assertEqual(nomes, {'Bruno'})

    def test_cpf_de_outra_unidade_mostra_so_o_basico_e_matricula(self):
        self.client.force_login(self.coord_b)
        response = self.client.get(self.url(self.violao), {'q': formatar(self.ana.cpf)})
        self.assertEqual(response.context['de_outra_unidade'], self.ana)
        self.assertNotContains(response, self.ana.nome_mae)
        response = self.client.post(self.url(self.violao), {'cpf': self.ana.cpf})
        self.assertRedirects(response, reverse('matriculas:oficina', args=[self.violao.pk]))
        self.assertTrue(Matricula.objects.filter(aluno=self.ana, oficina=self.violao).exists())

    def test_nao_matricula_aluno_invisivel_pelo_id(self):
        self.client.force_login(self.coord_b)
        response = self.client.post(self.url(self.violao), {'aluno': self.ana.pk})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Matricula.objects.exists())

    def test_coordenador_nao_abre_oficina_de_outra_unidade(self):
        self.client.force_login(self.coord_a)
        self.assertEqual(self.client.get(self.url(self.violao)).status_code, 404)

    def test_monitor_nao_matricula(self):
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.get(self.url(self.danca)).status_code, 403)
        self.assertEqual(self.client.post(self.url(self.danca), {'aluno': self.ana.pk}).status_code, 403)

    def test_recusa_vira_mensagem(self):
        regras.matricular(self.ana, self.danca, self.coord_a)
        self.client.force_login(self.coord_a)
        response = self.client.post(self.url(self.danca), {'aluno': self.ana.pk, 'q': 'Ana'}, follow=True)
        self.assertContains(response, 'já está cursando')


class ListaMatriculadosTests(BaseMatriculasTestCase):
    def setUp(self):
        regras.matricular(self.ana, self.danca, self.coord_a)
        FichaSaude.objects.create(aluno=self.ana, tipo_assistencia='SUS', possui_problema_saude=False,
                                  usa_medicacao_controlada=False, alergias='Dipirona')
        self.url = reverse('matriculas:oficina', args=[self.danca.pk])

    def test_monitor_designado_ve_lista_sem_link_para_cadastro_nem_saude(self):
        self.client.force_login(self.monitor)
        response = self.client.get(self.url)
        self.assertContains(response, 'Ana')
        self.assertNotContains(response, reverse('alunos:detalhe', args=[self.ana.pk]))
        self.assertNotContains(response, 'Alergia')  # LGPD: pode_ver_saude_emergencia é False para Monitor
        self.assertNotContains(response, 'Encerrar')

    def test_coordenador_ve_alerta_de_alergia_e_acoes(self):
        self.client.force_login(self.coord_a)
        response = self.client.get(self.url)
        self.assertContains(response, 'Alergia')
        self.assertContains(response, 'Encerrar')

    def test_acesso_barrado(self):
        for user in (self.outro_monitor, self.coord_b):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403, user)

    def test_concluir_pela_tela_e_historico(self):
        m = Matricula.objects.get(aluno=self.ana)
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('matriculas:concluir', args=[m.pk]), {'data': '2026-06-30', 'next': self.url})
        self.assertRedirects(response, self.url)
        self.assertNotContains(self.client.get(self.url), 'Ana')
        self.assertContains(self.client.get(self.url, {'situacao': 'todas'}), 'Concluído 30/06/2026')

    def test_alterar_situacao_barrado(self):
        m = Matricula.objects.get(aluno=self.ana)
        self.client.force_login(self.coord_b)
        self.assertEqual(self.client.post(reverse('matriculas:desistir', args=[m.pk])).status_code, 404)
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.post(reverse('matriculas:desistir', args=[m.pk])).status_code, 403)
        self.assertEqual(Matricula.objects.get(pk=m.pk).status, 'CURSANDO')

    def test_next_externo_e_ignorado(self):
        m = Matricula.objects.get(aluno=self.ana)
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('matriculas:desistir', args=[m.pk]), {'next': 'https://evil.example.com/'})
        self.assertRedirects(response, self.url)


class EtapaMatriculaTests(BaseMatriculasTestCase):
    def test_lista_opcoes_com_choque_e_matricula(self):
        regras.matricular(self.ana, self.danca, self.diretor)
        self.client.force_login(self.diretor)
        url = reverse('matriculas:aluno', args=[self.ana.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        opcoes = {o['oficina'].nome: o for o in response.context['opcoes']}
        self.assertNotIn('Dança', opcoes)  # já cursando
        self.assertTrue(opcoes['Violão']['conflitos'])
        self.assertFalse(opcoes['Teatro']['conflitos'])
        self.client.post(url, {'oficina': self.teatro.pk})
        self.assertTrue(Matricula.objects.filter(aluno=self.ana, oficina=self.teatro).exists())

    def test_coordenador_so_ve_oficinas_da_unidade(self):
        self.client.force_login(self.coord_a)
        response = self.client.get(reverse('matriculas:aluno', args=[self.ana.pk]))
        self.assertEqual({o['oficina'].nome for o in response.context['opcoes']}, {'Dança', 'Teatro'})

    def test_permissoes(self):
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.get(reverse('matriculas:aluno', args=[self.ana.pk])).status_code, 403)
        self.client.force_login(self.coord_b)
        self.assertEqual(self.client.get(reverse('matriculas:aluno', args=[self.ana.pk])).status_code, 404)
