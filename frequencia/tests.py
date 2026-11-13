from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection, IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from alunos.tests import criar_aluno, criar_usuario
from core.acesso import NivelAcesso
from escolas.foco import CHAVE_SESSAO
from escolas.models import EscolaNaica
from matriculas.models import Matricula
from oficinas.tests import criar_tag
from oficinas.tests import criar_oficina
from .models import Chamada, ChamadaGeral, RegistroAula

HOJE = timezone.localdate()


class ChamadaGeralTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = EscolaNaica.objects.create(nome='Naica Alfa')
        cls.b = EscolaNaica.objects.create(nome='Naica Beta')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord = criar_usuario('coord', NivelAcesso.COORDENADOR, cls.a)
        cls.monitor = criar_usuario('instrutor', NivelAcesso.MONITOR)
        cls.ana = criar_aluno(cls.a, 900000001, 'Ana')
        cls.bia = criar_aluno(cls.a, 900000002, 'Bia')
        Aluno.objects.filter(pk=cls.bia.pk).update(turno='TARDE', turma='B')
        cls.bia.refresh_from_db()
        cls.caio = criar_aluno(cls.b, 900000003, 'Caio')

    def url(self):
        return reverse('frequencia:chamada_naica')

    def dados(self, **extra):
        return {'escola': self.a.pk, 'data': HOJE.isoformat(),
                f'presenca_{self.ana.pk}': 'P', f'presenca_{self.bia.pk}': 'F', **extra}

    def test_alunos_sem_oficina_participam_e_salvam(self):
        self.client.force_login(self.coord)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, 'Ana')
        self.assertContains(resposta, 'Bia')
        self.assertEqual(resposta.context['total_alunos'], 2)
        self.assertNotContains(resposta, 'por oficina')
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 302)
        self.assertEqual(ChamadaGeral.objects.count(), 2)
        self.assertFalse(RegistroAula.objects.exists())
        self.assertFalse(Chamada.objects.exists())
        self.assertFalse(Matricula.objects.exists())

    def test_correcao_nao_duplica_e_preserva_autoria(self):
        self.client.force_login(self.coord)
        self.client.post(self.url(), self.dados())
        self.client.force_login(self.diretor)
        self.client.post(self.url(), self.dados(**{f'presenca_{self.ana.pk}': 'J', f'obs_{self.ana.pk}': 'Atestado'}))
        chamada = ChamadaGeral.objects.get(aluno=self.ana)
        self.assertEqual(ChamadaGeral.objects.count(), 2)
        self.assertEqual((chamada.status_presenca, chamada.observacoes), ('J', 'Atestado'))
        self.assertEqual((chamada.lancado_por, chamada.atualizado_por), (self.coord, self.diretor))

    def test_filtro_turno_preservado_e_nao_altera_outro_turno(self):
        self.client.force_login(self.coord)
        self.client.post(self.url(), self.dados())
        resposta = self.client.post(self.url(), self.dados(turno='MANHA', **{f'presenca_{self.ana.pk}': 'J', f'presenca_{self.bia.pk}': 'P'}))
        self.assertIn('turno=MANHA', resposta.url)
        self.assertEqual(ChamadaGeral.objects.get(aluno=self.bia).status_presenca, 'F')
        pagina = self.client.get(self.url(), {'turno': 'MANHA'})
        self.assertEqual(pagina.context['total_alunos'], 1)
        self.assertContains(pagina, 'Turma A')
        self.assertNotContains(pagina, 'Bia')

    def test_todos_os_turnos_e_legados_sem_turma(self):
        Aluno.objects.filter(pk=self.ana.pk).update(turno=None, turma=None)
        self.client.force_login(self.coord)
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.context['total_alunos'], 2)
        self.assertContains(resposta, 'Turma pendente')
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 302)
        self.assertEqual(ChamadaGeral.objects.count(), 2)

    def test_resposta_incompleta_ou_invalida_nao_salva_parcialmente(self):
        self.client.force_login(self.coord)
        for valor in ('', 'X'):
            resposta = self.client.post(self.url(), self.dados(**{f'presenca_{self.bia.pk}': valor}))
            self.assertContains(resposta, 'Marque a presença de Bia')
            self.assertContains(resposta, f'name="presenca_{self.ana.pk}"')
            self.assertFalse(ChamadaGeral.objects.exists())

    def test_data_futura_invalida_e_turno_invalido(self):
        self.client.force_login(self.coord)
        for dados in (self.dados(data='errada'), self.dados(data=(HOJE + timedelta(days=1)).isoformat()), self.dados(turno='NOITE')):
            self.assertEqual(self.client.post(self.url(), dados).status_code, 200)
            self.assertFalse(ChamadaGeral.objects.exists())

    def test_gestao_e_obrigatoria_inclusive_no_post(self):
        self.assertEqual(self.client.get(self.url()).status_code, 302)
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 403)
        self.assertFalse(ChamadaGeral.objects.exists())

    def test_coordenador_ignora_unidade_e_aluno_adulterados(self):
        self.client.force_login(self.coord)
        resposta = self.client.get(self.url(), {'escola': self.b.pk})
        self.assertEqual(resposta.context['escola'], self.a)
        self.client.post(self.url(), self.dados(escola=self.b.pk, **{f'presenca_{self.caio.pk}': 'P'}))
        self.assertFalse(ChamadaGeral.objects.filter(escola=self.b).exists())
        self.assertFalse(ChamadaGeral.objects.filter(aluno=self.caio).exists())

    def test_diretor_sem_foco_seleciona_unidade(self):
        self.client.force_login(self.diretor)
        self.assertIsNone(self.client.get(self.url()).context['escola'])
        resposta = self.client.post(self.url(), {'escola': self.b.pk, 'data': HOJE.isoformat(), f'presenca_{self.caio.pk}': 'P'})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(ChamadaGeral.objects.get().aluno, self.caio)

    def test_unidade_invalida_retorna_404(self):
        self.client.force_login(self.diretor)
        for unidade in ('errada', '99999999'):
            self.assertEqual(self.client.get(self.url(), {'escola': unidade}).status_code, 404)

    def test_diretor_em_foco_nao_expande_escopo(self):
        self.client.force_login(self.diretor)
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.a.pk
        sessao.save()
        resposta = self.client.get(self.url(), {'escola': self.b.pk})
        self.assertEqual(resposta.context['escola'], self.a)
        self.client.post(self.url(), self.dados(escola=self.b.pk))
        self.assertEqual(set(ChamadaGeral.objects.values_list('escola_id', flat=True)), {self.a.pk})

    def test_constraint_impede_duplicacao(self):
        ChamadaGeral.objects.create(escola=self.a, aluno=self.ana, data=HOJE, status_presenca='P')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChamadaGeral.objects.create(escola=self.a, aluno=self.ana, data=HOJE, status_presenca='F')

    def test_historico_continua_corrigivel_apos_mudanca_de_unidade(self):
        ontem = HOJE - timedelta(days=1)
        ChamadaGeral.objects.create(escola=self.a, aluno=self.ana, data=ontem, status_presenca='P')
        Aluno.objects.filter(pk=self.ana.pk).update(escola=self.b)
        self.client.force_login(self.coord)
        pagina = self.client.get(self.url(), {'data': ontem.isoformat()})
        self.assertContains(pagina, 'Ana')
        self.assertNotContains(self.client.get(self.url()), 'Ana')
        resposta = self.client.post(self.url(), self.dados(data=ontem.isoformat(), **{f'presenca_{self.ana.pk}': 'J'}))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(ChamadaGeral.objects.get(aluno=self.ana).status_presenca, 'J')

    def test_rotas_por_oficina_nao_permitem_escrita_nem_monitor(self):
        oficina = criar_oficina(criar_tag(escola=self.a, nome='Arte'))
        oficina.monitores.add(self.monitor)
        for nome, args in (('oficina', [oficina.pk]), ('chamada', [oficina.pk]), ('excluir_aula', [oficina.pk, 1])):
            url = reverse(f'frequencia:{nome}', args=args)
            self.client.force_login(self.coord)
            self.assertEqual(self.client.post(url, self.dados()).status_code, 405)
            self.assertEqual(self.client.get(url).status_code, 302)
            self.client.force_login(self.monitor)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, self.dados()).status_code, 403)
        self.assertFalse(ChamadaGeral.objects.exists())

    def test_consolidacao_preserva_originais_e_sinaliza_divergencias(self):
        tipo = criar_tag(escola=self.a, nome='Arte')
        for nome, presenca in (('Dança', 'P'), ('Teatro', 'F')):
            oficina = criar_oficina(tipo, nome)
            matricula = Matricula.objects.create(aluno=self.ana, oficina=oficina)
            registro = RegistroAula.objects.create(oficina=oficina, data_aula=HOJE, lancado_por=self.monitor)
            Chamada.objects.create(registro_aula=registro, matricula=matricula, status_presenca=presenca)
            outra = Matricula.objects.create(aluno=self.bia, oficina=oficina)
            Chamada.objects.create(registro_aula=registro, matricula=outra, status_presenca='J', observacoes='Atestado')
        consolidar = import_module('frequencia.migrations.0003_consolidar_historico').consolidar
        editor = SimpleNamespace(connection=connection)
        consolidar(apps, editor)
        self.assertEqual(Chamada.objects.count(), 4)
        self.assertEqual(ChamadaGeral.objects.count(), 2)
        self.assertEqual(ChamadaGeral.objects.get(aluno=self.ana).status_presenca, '')
        self.assertEqual(ChamadaGeral.objects.get(aluno=self.bia).status_presenca, 'J')
        self.client.force_login(self.coord)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, 'presenças divergentes')
        self.client.post(self.url(), self.dados())
        consolidar(apps, editor)
        self.assertEqual(ChamadaGeral.objects.get(aluno=self.ana).status_presenca, 'P')
        self.assertEqual(Chamada.objects.count(), 4)
