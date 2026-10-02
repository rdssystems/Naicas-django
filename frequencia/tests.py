from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.tests import criar_aluno, criar_usuario
from core.acesso import NivelAcesso
from escolas.models import EscolaNaica
from matriculas import regras as regras_matricula
from matriculas.models import Matricula
from oficinas.models import Oficina, TipoOficina
from oficinas.tests import criar_oficina

from . import regras
from .models import Chamada, RegistroAula

HOJE = timezone.localdate()


def dia_da_semana_anterior(weekday, a_partir=HOJE):
    """Última data (antes de `a_partir`) que cai no dia da semana dado."""
    d = a_partir - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


class BaseFrequenciaTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.escola_a = EscolaNaica.objects.create(nome='Naica Centro')
        cls.escola_b = EscolaNaica.objects.create(nome='Naica Norte')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord_a = criar_usuario('coord_a', NivelAcesso.COORDENADOR, cls.escola_a)
        cls.coord_b = criar_usuario('coord_b', NivelAcesso.COORDENADOR, cls.escola_b)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.outro_monitor = criar_usuario('outro_monitor', NivelAcesso.MONITOR)
        tipo = TipoOficina.objects.create(escola=cls.escola_a, nome='Dança')
        cls.oficina = criar_oficina(
            tipo, 'Dança', dias_semana=[0, 2, 4], data_inicio=HOJE - timedelta(days=90),
            data_fim=HOJE + timedelta(days=90), vagas=10,
        )
        cls.oficina.monitores.add(cls.monitor)
        cls.ana = criar_aluno(cls.escola_a, 900000001, 'Ana')
        cls.bia = criar_aluno(cls.escola_a, 900000002, 'Bia')
        cls.caio = criar_aluno(cls.escola_a, 900000003, 'Caio')
        inicio = HOJE - timedelta(days=60)
        for aluno in (cls.ana, cls.bia, cls.caio):
            regras_matricula.matricular(aluno, cls.oficina, cls.coord_a)
        # Matrículas "antigas" (data_inscricao é auto_now_add).
        Matricula.objects.filter(oficina=cls.oficina).update(data_inscricao=inicio)
        cls.seg = dia_da_semana_anterior(0)
        cls.ter = dia_da_semana_anterior(1)

    def m(self, aluno):
        return Matricula.objects.get(aluno=aluno, oficina=self.oficina, status='CURSANDO')

    def url_chamada(self, data=None):
        url = reverse('frequencia:chamada', args=[self.oficina.pk])
        return f'{url}?data={data.isoformat()}' if data else url

    def lancar(self, data, presencas, user=None, follow=False, **extra):
        self.client.force_login(user or self.monitor)
        dados = {'data': data.isoformat(), **extra}
        for aluno, valor in presencas.items():
            dados[f'presenca_{self.m(aluno).pk}'] = valor
        return self.client.post(self.url_chamada(), dados, follow=follow)


class ValidacaoDataTests(BaseFrequenciaTestCase):
    def test_regras_de_data(self):
        self.assertIsNone(regras.validar_data_aula(self.oficina, self.seg))
        self.assertIn('reposição', regras.validar_data_aula(self.oficina, self.ter))
        with self.assertRaisesMessage(regras.DataInvalida, 'futura'):
            regras.validar_data_aula(self.oficina, HOJE + timedelta(days=1))
        with self.assertRaisesMessage(regras.DataInvalida, 'período'):
            regras.validar_data_aula(self.oficina, self.oficina.data_inicio - timedelta(days=1))

    def test_oficina_arquivada_nao_recebe(self):
        Oficina.objects.filter(pk=self.oficina.pk).update(status=Oficina.Status.ARQUIVADO)
        self.oficina.refresh_from_db()
        with self.assertRaises(regras.DataInvalida):
            regras.validar_data_aula(self.oficina, self.seg)

    def test_data_invalida_volta_com_mensagem(self):
        self.client.force_login(self.monitor)
        response = self.client.get(self.url_chamada(HOJE + timedelta(days=3)), follow=True)
        self.assertContains(response, 'data futura')


class LancamentoTests(BaseFrequenciaTestCase):
    def test_monitor_lanca_chamada(self):
        response = self.lancar(self.seg, {self.ana: 'P', self.bia: 'F', self.caio: 'J'},
                               **{'observacoes': 'Coreografia nova'})
        self.assertRedirects(response, reverse('frequencia:oficina', args=[self.oficina.pk]))
        aula = RegistroAula.objects.get(oficina=self.oficina, data_aula=self.seg)
        self.assertEqual(aula.lancado_por, self.monitor)
        self.assertEqual(aula.observacoes, 'Coreografia nova')
        self.assertEqual(
            dict(aula.chamadas.values_list('matricula__aluno__nome', 'status_presenca')),
            {'Ana': 'P', 'Bia': 'F', 'Caio': 'J'},
        )

    def test_corrigir_nao_duplica_e_registra_quem_alterou(self):
        self.lancar(self.seg, {self.ana: 'P', self.bia: 'P', self.caio: 'P'})
        self.lancar(self.seg, {self.ana: 'F', self.bia: 'P', self.caio: 'P'}, user=self.coord_a)
        aula = RegistroAula.objects.get(oficina=self.oficina, data_aula=self.seg)
        self.assertEqual(RegistroAula.objects.count(), 1)
        self.assertEqual(aula.chamadas.count(), 3)
        self.assertEqual(aula.chamadas.get(matricula__aluno=self.ana).status_presenca, 'F')
        self.assertEqual((aula.lancado_por, aula.atualizado_por), (self.monitor, self.coord_a))

    def test_todos_precisam_ter_presenca(self):
        response = self.lancar(self.seg, {self.ana: 'P', self.bia: 'P'}, follow=True)
        self.assertContains(response, 'Marque a presença de Caio')
        self.assertFalse(RegistroAula.objects.exists())

    def test_valor_invalido_e_recusado(self):
        response = self.lancar(self.seg, {self.ana: 'X', self.bia: 'P', self.caio: 'P'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RegistroAula.objects.exists())

    def test_tela_comeca_com_todos_presentes(self):
        self.client.force_login(self.monitor)
        response = self.client.get(self.url_chamada(self.seg))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['linhas']), 3)
        self.assertContains(response, 'value="P" autocomplete="off" checked', count=3)

    def test_so_matriculas_ativas_na_data(self):
        novo = criar_aluno(self.escola_a, 900000004, 'Davi')
        regras_matricula.matricular(novo, self.oficina, self.coord_a)  # inscrito hoje
        saiu = self.m(self.caio)
        regras_matricula.registrar_desistencia(saiu, self.coord_a, self.seg - timedelta(days=7))
        nomes = {m.aluno.nome for m in regras.matriculas_ativas_na_data(self.oficina, self.seg)}
        self.assertEqual(nomes, {'Ana', 'Bia'})  # Davi ainda não; Caio já tinha saído
        desistiu_depois = self.m(self.bia)
        regras_matricula.registrar_desistencia(desistiu_depois, self.coord_a, HOJE)
        nomes = {m.aluno.nome for m in regras.matriculas_ativas_na_data(self.oficina, self.seg)}
        self.assertEqual(nomes, {'Ana', 'Bia'})  # Bia saiu depois da aula: continua


class PermissoesTests(BaseFrequenciaTestCase):
    def test_quem_acessa(self):
        url = reverse('frequencia:oficina', args=[self.oficina.pk])
        for user, esperado in (
            (self.monitor, 200), (self.coord_a, 200), (self.diretor, 200),
            (self.outro_monitor, 403), (self.coord_b, 403),
        ):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, esperado, user)
            self.assertEqual(self.client.get(self.url_chamada(self.seg)).status_code, esperado, user)

    def test_monitor_nao_designado_nao_lanca(self):
        response = self.lancar(self.seg, {self.ana: 'P', self.bia: 'P', self.caio: 'P'}, user=self.outro_monitor)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(RegistroAula.objects.exists())

    def test_so_gestao_exclui_aula(self):
        self.lancar(self.seg, {self.ana: 'P', self.bia: 'P', self.caio: 'P'})
        aula = RegistroAula.objects.get()
        url = reverse('frequencia:excluir_aula', args=[self.oficina.pk, aula.pk])
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.coord_a)
        self.client.post(url)
        self.assertFalse(RegistroAula.objects.exists())
        self.assertFalse(Chamada.objects.exists())


class ResumoTests(BaseFrequenciaTestCase):
    def test_percentual_conta_justificada_como_presenca(self):
        self.lancar(self.seg, {self.ana: 'P', self.bia: 'F', self.caio: 'J'})
        self.lancar(self.seg - timedelta(days=2), {self.ana: 'P', self.bia: 'F', self.caio: 'F'})
        resumo = {r['matricula'].aluno.nome: r for r in regras.resumo_por_matricula(self.oficina)}
        self.assertEqual(resumo['Ana']['percentual'], 100)
        self.assertEqual(resumo['Bia']['percentual'], 0)
        self.assertEqual(resumo['Caio']['percentual'], 50)
        self.assertEqual((resumo['Caio']['matricula'].faltas, resumo['Caio']['matricula'].justificadas), (1, 1))

    def test_tela_de_frequencia_mostra_aulas_e_resumo(self):
        self.lancar(self.seg, {self.ana: 'P', self.bia: 'F', self.caio: 'P'})
        self.client.force_login(self.monitor)
        response = self.client.get(reverse('frequencia:oficina', args=[self.oficina.pk]))
        self.assertContains(response, self.seg.strftime('%d/%m/%Y'))
        self.assertNotContains(response, 'Excluir chamada')  # Monitor não exclui
