from html.parser import HTMLParser
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Permission
from django.db import connection
from django.urls import reverse

from frequencia.models import ChamadaGeral

from .forms import StatusAlunoForm
from .models import Aluno
from .tests import BaseAlunosTestCase


class TextosVisiveis(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.partes = []
        self.ignorar = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.ignorar = True
        for nome, valor in attrs:
            if nome in ('title', 'aria-label', 'placeholder', 'alt') and valor:
                self.partes.append(valor)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.ignorar = False

    def handle_data(self, data):
        if not self.ignorar:
            self.partes.append(data)


class TerminologiaTests(BaseAlunosTestCase):
    def test_telas_usam_atendido_e_preservam_destinos(self):
        for user in (self.diretor, self.coord_a):
            self.client.force_login(user)
            destinos = [
                ('core:home', []), ('dashboard:painel', []), ('alunos:lista', []),
                ('alunos:criar', []), ('alunos:detalhe', [self.aluno_a.pk]),
                ('alunos:etapa_dados', [self.aluno_a.pk]),
                ('alunos:etapa_responsaveis', [self.aluno_a.pk]),
                ('alunos:etapa_familia', [self.aluno_a.pk]),
                ('alunos:etapa_saude', [self.aluno_a.pk]),
                ('anexos:aluno', [self.aluno_a.pk]), ('matriculas:aluno', [self.aluno_a.pk]),
                ('frequencia:chamada_naica', []),
            ]
            for destino, args in destinos:
                with self.subTest(user=user.username, destino=destino):
                    resposta = self.client.get(reverse(destino, args=args), {'escola': self.escola_a.pk})
                    self.assertEqual(resposta.status_code, 200)
                    textos = ' '.join(TextosVisiveis(resposta.content.decode()).partes)
                    self.assertNotRegex(textos, r'(?i)\balunos?\b')
                    self.assertIn('Atendidos', textos)
            lista = self.client.get(reverse('alunos:lista'))
            self.assertContains(lista, reverse('alunos:detalhe', args=[self.aluno_a.pk]))

    def test_administrativo_e_formularios_usam_novos_rotulos(self):
        self.assertEqual(apps.get_app_config('alunos').verbose_name, 'Atendidos')
        self.assertEqual(Aluno._meta.verbose_name, 'atendido')
        self.assertEqual(Aluno._meta.verbose_name_plural, 'atendidos')
        self.assertEqual(Aluno.Status.values, ['ATIVO', 'INATIVO'])
        self.assertEqual(list(StatusAlunoForm().fields['status'].choices), [('INATIVO', 'Inativo')])
        for model in apps.get_models():
            for field in model._meta.fields:
                if field.name == 'aluno':
                    self.assertEqual(field.verbose_name, 'atendido', model._meta.label)

    def test_migracao_consolida_desligados_sem_apagar_historico_ou_permissoes(self):
        from django.utils import timezone

        Aluno.objects.filter(pk=self.aluno_a.pk).update(status='DESLIGADO')
        chamada = ChamadaGeral.objects.create(
            aluno=self.aluno_a, escola=self.escola_a, data=timezone.localdate(), status_presenca='P',
        )
        permissao = Permission.objects.get(content_type__app_label='alunos', codename='view_aluno')
        Permission.objects.filter(pk=permissao.pk).update(name='Can view aluno')
        self.coord_a.user_permissions.add(permissao)
        migracao = import_module('alunos.migrations.0008_atendidos_e_inativacao')
        migracao.consolidar_inativos_e_rotulos(apps, SimpleNamespace(connection=connection))
        self.aluno_a.refresh_from_db()
        permissao.refresh_from_db()
        self.assertEqual(self.aluno_a.status, Aluno.Status.INATIVO)
        self.assertEqual(Aluno.objects.count(), 2)
        self.assertEqual(ChamadaGeral.objects.get(pk=chamada.pk).status_presenca, 'P')
        self.assertEqual(permissao.name, 'Can view atendido')
        self.assertTrue(self.coord_a.user_permissions.filter(pk=permissao.pk).exists())

    def test_renomeia_tipo_de_documento_preservando_vinculos_e_nomes_ja_existentes(self):
        from anexos.models import Anexo, TipoDocumento

        tipo = TipoDocumento.objects.create(nome='Ficha do aluno')
        existente = TipoDocumento.objects.create(nome='Ficha do atendido')
        anexo = Anexo.objects.create(
            aluno=self.aluno_a, tipo_documento=tipo, arquivo='anexos/referencia.pdf',
            nome_original='documento original.pdf', tamanho=3,
        )
        migracao = import_module('anexos.migrations.0003_atendidos_e_inativacao')
        migracao.atualizar_tipos_documento(apps, SimpleNamespace(connection=connection))
        tipo.refresh_from_db()
        existente.refresh_from_db()
        anexo.refresh_from_db()
        self.assertIn('atendido', tipo.nome)
        self.assertNotIn('aluno', tipo.nome)
        self.assertNotEqual(tipo.nome, existente.nome)
        self.assertEqual(existente.nome, 'Ficha do atendido')
        self.assertEqual(anexo.tipo_documento_id, tipo.pk)
        self.assertEqual(anexo.arquivo.name, 'anexos/referencia.pdf')
