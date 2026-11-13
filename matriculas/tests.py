from datetime import time

from django.test import TestCase
from django.urls import reverse

from alunos.tests import criar_aluno, criar_usuario
from core.acesso import NivelAcesso
from escolas.models import EscolaNaica
from oficinas.models import AtividadeCronograma, Oficina

from .models import Matricula


class CronogramaAlunoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = EscolaNaica.objects.create(nome='Alfa')
        cls.b = EscolaNaica.objects.create(nome='Beta')
        cls.coord = criar_usuario('coord', NivelAcesso.COORDENADOR, cls.a)
        cls.outro = criar_usuario('outro', NivelAcesso.COORDENADOR, cls.b)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.aluno = criar_aluno(cls.a, 933000001, 'Ana')
        cls.arte = Oficina.objects.create(nome='Arte')
        cls.horario = AtividadeCronograma.objects.create(
            escola=cls.a, oficina=cls.arte, turno='MANHA', turmas=['A'],
            dias_semana=[0], horario=time(8), horario_fim=time(10),
        )

    def url(self):
        return reverse('matriculas:aluno', args=[self.aluno.pk])

    def test_exibe_somente_unidade_turno_turma_ativos(self):
        for escola, turno, turmas in ((self.a, 'MANHA', ['B']), (self.a, 'TARDE', ['A']), (self.b, 'MANHA', ['A'])):
            AtividadeCronograma.objects.create(
                escola=escola, oficina=self.arte, turno=turno, turmas=turmas,
                dias_semana=[1], horario=time(13), horario_fim=time(14),
            )
        self.client.force_login(self.coord)
        resposta = self.client.get(self.url())
        self.assertEqual(list(resposta.context['oficinas']), [self.horario])
        self.assertFalse(Matricula.objects.exists())
        self.assertContains(resposta, 'Cronograma da turma')

    def test_arquivar_e_excluir_oficina_remove_do_cronograma_do_aluno(self):
        self.client.force_login(self.coord)
        self.arte.arquivada = True
        self.arte.save()
        self.assertFalse(self.client.get(self.url()).context['oficinas'].exists())
        self.arte.delete()
        self.assertFalse(self.client.get(self.url()).context['oficinas'].exists())

    def test_classificacao_pendente(self):
        self.aluno.turma = None
        self.aluno.save(update_fields=['turma'])
        self.client.force_login(self.coord)
        self.assertContains(self.client.get(self.url()), 'Defina o turno e a turma')

    def test_permissoes(self):
        for user, codigo in ((self.outro, 404), (self.monitor, 403)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url()).status_code, codigo)

    def test_rotas_antigas_nao_alteram_historicos(self):
        matricula = Matricula.objects.create(aluno=self.aluno, oficina=self.horario)
        self.client.force_login(self.coord)
        for nome, args in (('aluno', [self.aluno.pk]), ('matricular_na_oficina', [self.horario.pk]),
                           ('concluir', [matricula.pk]), ('desistir', [matricula.pk])):
            self.assertEqual(self.client.post(reverse(f'matriculas:{nome}', args=args)).status_code, 405)
        self.assertEqual(Matricula.objects.count(), 1)

    def test_endereco_antigo_redireciona_ao_horario(self):
        self.client.force_login(self.coord)
        self.assertRedirects(self.client.get(reverse('matriculas:oficina', args=[self.horario.pk])),
                             reverse('escalas:detalhe', args=[self.horario.pk]))

    def test_etapa_cronograma_nao_depende_de_matricula(self):
        self.assertEqual(self.aluno.etapas()[5][1], 'Cronograma')
        self.assertTrue(self.aluno.etapas()[5][3])
        self.assertFalse(Matricula.objects.exists())
