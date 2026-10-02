import io
import os
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from alunos.models import AlunoResponsavel, ContatoEmergencia, FichaSaude
from alunos.tests import criar_aluno, criar_responsavel, criar_usuario
from core.acesso import NivelAcesso
from escolas.models import EscolaNaica

from .management.commands.popular_anexos import pdf_ficticio
from .models import Anexo, TipoDocumento
from .validators import validar_arquivo

PDF = b'%PDF-1.4\n%fake\n'


def imagem(formato='PNG'):
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), 'red').save(buffer, formato)
    return buffer.getvalue()


def upload(nome, conteudo):
    return SimpleUploadedFile(nome, conteudo)


class ValidadorTests(TestCase):
    def test_aceita_pdf_e_imagens(self):
        validar_arquivo(upload('doc.pdf', PDF))
        validar_arquivo(upload('foto.png', imagem('PNG')))
        validar_arquivo(upload('foto.JPG', imagem('JPEG')))
        validar_arquivo(upload('foto.webp', imagem('WEBP')))

    def test_recusa_formato_e_conteudo_falso(self):
        casos = [
            upload('virus.exe', b'MZ...'),
            upload('planilha.docx', b'PK...'),
            upload('falso.pdf', b'MZ executavel renomeado'),
            upload('troca.jpg', imagem('PNG')),  # PNG com extensão .jpg
            upload('quebrada.png', b'\x89PNG lixo'),
        ]
        for arquivo in casos:
            with self.assertRaises(ValidationError, msg=arquivo.name):
                validar_arquivo(arquivo)

    def test_recusa_maior_que_10mb(self):
        with self.assertRaises(ValidationError):
            validar_arquivo(upload('grande.pdf', PDF + b'0' * (10 * 1024 * 1024)))

    def test_pdf_ficticio_e_valido(self):
        validar_arquivo(upload('f.pdf', pdf_ficticio('Teste (com parênteses)')))


class BaseAnexosTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.escola_a = EscolaNaica.objects.create(nome='Naica Centro')
        cls.escola_b = EscolaNaica.objects.create(nome='Naica Norte')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord_a = criar_usuario('coord_a', NivelAcesso.COORDENADOR, cls.escola_a)
        cls.coord_b = criar_usuario('coord_b', NivelAcesso.COORDENADOR, cls.escola_b)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.aluno_a = criar_aluno(cls.escola_a, 700000001, 'Ana')
        cls.aluno_b = criar_aluno(cls.escola_b, 700000002, 'Bruno')
        cls.obrigatorios = list(TipoDocumento.objects.filter(obrigatorio=True, ativo=True))
        cls.opcional = TipoDocumento.objects.filter(obrigatorio=False).first()

    def enviar(self, aluno, tipo, arquivo):
        return self.client.post(
            reverse('anexos:aluno', args=[aluno.pk]), {'tipo_documento': tipo.pk, 'arquivo': arquivo}
        )

    def criar_anexo(self, aluno, tipo):
        anexo = Anexo(aluno=aluno, tipo_documento=tipo, nome_original='rg.pdf', tamanho=len(PDF))
        anexo.arquivo.save('rg.pdf', ContentFile(PDF), save=True)
        return anexo


class EnvioTests(BaseAnexosTestCase):
    def test_tipos_padrao_criados_pela_migracao(self):
        self.assertEqual(len(self.obrigatorios), 6)
        self.assertEqual(TipoDocumento.objects.count(), 10)

    def test_coordenador_envia_para_aluno_da_unidade(self):
        self.client.force_login(self.coord_a)
        tipo = self.obrigatorios[0]
        response = self.enviar(self.aluno_a, tipo, upload('RG da Ana Silva.pdf', PDF))
        self.assertRedirects(response, reverse('anexos:aluno', args=[self.aluno_a.pk]))
        anexo = Anexo.objects.get(aluno=self.aluno_a)
        self.assertEqual(anexo.nome_original, 'RG da Ana Silva.pdf')
        self.assertEqual(anexo.enviado_por, self.coord_a)
        self.assertNotIn('Ana', anexo.arquivo.name)  # nome original fora do caminho
        self.assertTrue(os.path.exists(anexo.arquivo.path))

    def test_varios_arquivos_por_tipo(self):
        self.client.force_login(self.coord_a)
        tipo = self.obrigatorios[0]
        self.enviar(self.aluno_a, tipo, upload('frente.jpg', imagem('JPEG')))
        self.enviar(self.aluno_a, tipo, upload('verso.jpg', imagem('JPEG')))
        self.assertEqual(Anexo.objects.filter(aluno=self.aluno_a, tipo_documento=tipo).count(), 2)

    def test_arquivo_invalido_mostra_erro_na_linha_do_tipo(self):
        self.client.force_login(self.coord_a)
        tipo = self.obrigatorios[1]
        response = self.enviar(self.aluno_a, tipo, upload('falso.pdf', b'nao sou pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Anexo.objects.exists())
        linha = next(l for l in response.context['linhas'] if l['tipo'] == tipo)
        self.assertIn('arquivo', linha['form'].errors)

    def test_tipo_desativado_nao_recebe_envio(self):
        tipo = self.opcional
        tipo.ativo = False
        tipo.save()
        self.client.force_login(self.coord_a)
        response = self.enviar(self.aluno_a, tipo, upload('a.pdf', PDF))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Anexo.objects.exists())

    def test_permissoes_de_envio(self):
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.get(reverse('anexos:aluno', args=[self.aluno_a.pk])).status_code, 403)
        self.client.force_login(self.coord_a)
        response = self.enviar(self.aluno_b, self.obrigatorios[0], upload('a.pdf', PDF))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Anexo.objects.exists())

    def test_tela_renderiza(self):
        self.criar_anexo(self.aluno_a, self.obrigatorios[0])
        self.client.force_login(self.coord_a)
        response = self.client.get(reverse('anexos:aluno', args=[self.aluno_a.pk]))
        self.assertContains(response, 'Faltam 5 documentos obrigatórios')
        self.assertContains(response, 'rg.pdf')


class DownloadExclusaoTests(BaseAnexosTestCase):
    def setUp(self):
        self.anexo = self.criar_anexo(self.aluno_a, self.obrigatorios[0])

    def test_download_inline_para_quem_ve_o_aluno(self):
        for user in (self.coord_a, self.diretor):
            self.client.force_login(user)
            response = self.client.get(reverse('anexos:arquivo', args=[self.anexo.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), PDF)
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertTrue(response['Content-Disposition'].startswith('inline'))
            self.assertIn('no-store', response['Cache-Control'])

    def test_download_barrado(self):
        url = reverse('anexos:arquivo', args=[self.anexo.pk])
        self.assertEqual(self.client.get(url).status_code, 302)  # anônimo -> login
        self.client.force_login(self.coord_b)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_media_nao_e_servido_publicamente(self):
        self.client.force_login(self.diretor)
        self.assertEqual(self.client.get('/media/' + self.anexo.arquivo.name).status_code, 404)

    def test_excluir_apaga_o_arquivo_do_disco(self):
        caminho = self.anexo.arquivo.path
        self.client.force_login(self.coord_a)
        self.client.post(reverse('anexos:excluir', args=[self.anexo.pk]))
        self.assertFalse(Anexo.objects.filter(pk=self.anexo.pk).exists())
        self.assertFalse(os.path.exists(caminho))

    def test_coordenador_de_outra_unidade_nao_exclui(self):
        self.client.force_login(self.coord_b)
        response = self.client.post(reverse('anexos:excluir', args=[self.anexo.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Anexo.objects.filter(pk=self.anexo.pk).exists())


class CadastroCompletoTests(BaseAnexosTestCase):
    def completar_etapas_1_a_4(self, aluno):
        AlunoResponsavel.objects.create(aluno=aluno, responsavel=criar_responsavel(710000001), grau_parentesco='MAE')
        for nome in ('A', 'B'):
            ContatoEmergencia.objects.create(aluno=aluno, nome=nome, parentesco='TIO', celular='1')
        FichaSaude.objects.create(aluno=aluno, tipo_assistencia='SUS', possui_problema_saude=False,
                                  usa_medicacao_controlada=False)

    def test_falta_de_obrigatorio_impede_selo(self):
        self.completar_etapas_1_a_4(self.aluno_a)
        for tipo in self.obrigatorios[:-1]:
            self.criar_anexo(self.aluno_a, tipo)
        aluno = type(self.aluno_a).objects.get(pk=self.aluno_a.pk)
        self.assertFalse(aluno.cadastro_completo)
        self.criar_anexo(self.aluno_a, self.obrigatorios[-1])
        aluno = type(self.aluno_a).objects.get(pk=self.aluno_a.pk)
        self.assertTrue(aluno.cadastro_completo)
        self.assertTrue(aluno.etapas()[4][3])

    def test_opcional_nao_e_exigido_e_desativar_obrigatorio_libera(self):
        self.completar_etapas_1_a_4(self.aluno_a)
        for tipo in self.obrigatorios[1:]:
            self.criar_anexo(self.aluno_a, tipo)
        TipoDocumento.objects.filter(pk=self.obrigatorios[0].pk).update(ativo=False)
        aluno = type(self.aluno_a).objects.get(pk=self.aluno_a.pk)
        self.assertTrue(aluno.cadastro_completo)

    def test_lista_de_alunos_sem_query_por_aluno_para_anexos(self):
        self.client.force_login(self.diretor)
        response = self.client.get(reverse('alunos:lista'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incompleto')


class TiposDocumentoTests(BaseAnexosTestCase):
    def test_so_diretor_gerencia(self):
        urls = [reverse('anexos:tipos'), reverse('anexos:tipo_criar'),
                reverse('anexos:tipo_editar', args=[self.opcional.pk])]
        for user in (self.coord_a, self.monitor):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, (user, url))
        self.client.force_login(self.diretor)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_diretor_cria_tipo_obrigatorio(self):
        self.client.force_login(self.diretor)
        self.client.post(reverse('anexos:tipo_criar'), {'nome': 'Vacinação', 'obrigatorio': 'on', 'ativo': 'on', 'ordem': 5})
        self.assertTrue(TipoDocumento.objects.get(nome='Vacinação').obrigatorio)

    def test_tipo_em_uso_nao_e_excluido(self):
        self.criar_anexo(self.aluno_a, self.obrigatorios[0])
        self.client.force_login(self.diretor)
        self.client.post(reverse('anexos:tipo_excluir', args=[self.obrigatorios[0].pk]))
        self.assertTrue(TipoDocumento.objects.filter(pk=self.obrigatorios[0].pk).exists())
        self.client.post(reverse('anexos:tipo_excluir', args=[self.opcional.pk]))
        self.assertFalse(TipoDocumento.objects.filter(pk=self.opcional.pk).exists())


class PopularAnexosTests(BaseAnexosTestCase):
    def test_preenche_obrigatorios_pendentes(self):
        with override_settings(DEBUG=True):
            call_command('popular_anexos', aluno=[self.aluno_a.pk], stdout=io.StringIO())
        self.assertEqual(Anexo.objects.filter(aluno=self.aluno_a).count(), 6)
        for anexo in Anexo.objects.filter(aluno=self.aluno_a):
            with anexo.arquivo.open('rb') as f:
                validar_arquivo(SimpleUploadedFile('x.pdf', f.read()))
