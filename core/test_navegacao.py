from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from alunos.tests import BaseAlunosTestCase
from escolas.foco import CHAVE_SESSAO

from .navegacao import retorno_da_pagina


class RetornoTests(SimpleTestCase):
    def retorno(self, caminho, anterior='', secure=False):
        request = RequestFactory().get(caminho, HTTP_REFERER=anterior, secure=secure)
        request.user = AnonymousUser()
        return retorno_da_pagina(request)

    def test_preserva_filtros_e_paginacao_da_visualizacao_anterior(self):
        retorno = self.retorno('/alunos/1/', 'http://testserver/alunos/?q=Ana&turno=MANHA&page=2')
        self.assertEqual(retorno, {
            'voltar_url': '/alunos/?q=Ana&turno=MANHA&page=2', 'voltar_historico': True,
        })

    def test_ignora_destinos_externos_autenticacao_e_a_propria_pagina(self):
        for anterior in ('https://outro.exemplo/alunos/', '//outro.exemplo/',
                         'https://testserver.outro.exemplo/', 'javascript:alert(1)',
                         'http://testserver/usuarios/login/?next=/alunos/1/',
                         '/usuarios/logout/', '/alunos/1/', 'alunos/'):
            with self.subTest(anterior=anterior):
                self.assertEqual(self.retorno('/alunos/1/', anterior), {
                    'voltar_url': '/alunos/', 'voltar_historico': False,
                })

    def test_https_nao_volta_para_referencia_http(self):
        self.assertFalse(self.retorno('/alunos/1/', 'http://testserver/alunos/', secure=True)['voltar_historico'])
        self.assertTrue(self.retorno('/alunos/1/', 'https://testserver/alunos/', secure=True)['voltar_historico'])

    def test_acesso_direto_tem_destino_contextual(self):
        for caminho, destino in (
            ('/alunos/1/', '/alunos/'), ('/alunos/1/saude/', '/alunos/1/'),
            ('/alunos/novo/', '/alunos/'), ('/anexos/aluno/1/', '/alunos/1/'),
            ('/matriculas/aluno/1/', '/alunos/1/'), ('/oficinas/1/editar/', '/oficinas/1/'),
            ('/escalas/atividades/1/editar/', '/escalas/atividades/1/'),
            ('/escolas/nova/', '/escolas/'), ('/usuarios/novo/', '/usuarios/'),
        ):
            with self.subTest(caminho=caminho):
                self.assertEqual(self.retorno(caminho)['voltar_url'], destino)

    def test_login_inicial_nao_cria_retorno_em_circulo(self):
        self.assertIsNone(self.retorno('/usuarios/login/')['voltar_url'])


class NavegacaoPorPerfilTests(BaseAlunosTestCase):
    def test_menu_modal_preserva_destinos_por_perfil(self):
        for user in (self.diretor, self.coord_a, self.monitor):
            self.client.force_login(user)
            resposta = self.client.get(reverse('core:home'))
            self.assertContains(resposta, 'id="menu-principal"')
            self.assertContains(resposta, 'id="menu-desktop"', count=1)
            self.assertNotContains(resposta, 'id="voltar-pagina"')
            self.assertContains(resposta, 'data-bs-backdrop="true"')
            self.assertContains(resposta, 'data-bs-scroll="false"')
            self.assertContains(resposta, 'data-bs-keyboard="true"')
            self.assertContains(resposta, 'data-bs-target="#menu-principal"')
            self.assertContains(resposta, 'aria-controls="menu-principal"')
            self.assertContains(resposta, 'Voltar à página')
            self.assertNotContains(resposta, 'navbar-collapse')
            self.assertContains(resposta, f'action="{reverse("usuarios:logout")}"')
            self.assertContains(resposta, 'csrfmiddlewaretoken')
            for destino in ('core:home', 'oficinas:lista', 'escalas:grade'):
                self.assertContains(resposta, f'href="{reverse(destino)}"')
            for destino in ('escolas:lista', 'usuarios:lista', 'anexos:tipos'):
                verificar = self.assertContains if user == self.diretor else self.assertNotContains
                verificar(resposta, f'href="{reverse(destino)}"')
            for destino in ('dashboard:painel', 'alunos:lista'):
                verificar = self.assertNotContains if user == self.monitor else self.assertContains
                verificar(resposta, f'href="{reverse(destino)}"')

    def test_um_botao_voltar_em_listas_fichas_formularios_e_cronograma(self):
        self.client.force_login(self.diretor)
        destinos = [
            ('core:home', []), ('dashboard:painel', []), ('alunos:lista', []),
            ('alunos:criar', []), ('alunos:detalhe', [self.aluno_a.pk]),
            ('alunos:etapa_dados', [self.aluno_a.pk]), ('alunos:etapa_responsaveis', [self.aluno_a.pk]),
            ('alunos:etapa_familia', [self.aluno_a.pk]), ('alunos:etapa_saude', [self.aluno_a.pk]),
            ('anexos:aluno', [self.aluno_a.pk]), ('anexos:tipos', []), ('anexos:tipo_criar', []),
            ('matriculas:aluno', [self.aluno_a.pk]), ('frequencia:chamada_naica', []),
            ('escalas:grade', []), ('escalas:criar', []), ('oficinas:lista', []),
            ('oficinas:criar', []), ('escolas:lista', []), ('escolas:criar', []),
            ('usuarios:lista', []), ('usuarios:criar', []),
        ]
        for destino, args in destinos:
            with self.subTest(destino=destino):
                resposta = self.client.get(reverse(destino, args=args))
                self.assertEqual(resposta.status_code, 200)
                if destino == 'core:home':
                    self.assertNotContains(resposta, 'id="voltar-pagina"')
                else:
                    self.assertContains(resposta, 'id="voltar-pagina"', count=1)
                self.assertContains(resposta, 'core/navegacao.js')

    def test_retorno_filtrado_renderiza_destino_e_habilita_historico(self):
        self.client.force_login(self.coord_a)
        resposta = self.client.get(reverse('alunos:detalhe', args=[self.aluno_a.pk]),
                                   HTTP_REFERER='http://testserver/alunos/?q=Ana&page=2')
        self.assertContains(resposta, 'href="/alunos/?q=Ana&amp;page=2"')
        self.assertContains(resposta, 'data-historico="true"')

    def test_seletor_de_unidade_e_somente_do_diretor_e_preserva_foco(self):
        self.client.force_login(self.diretor)
        self.client.post(reverse('escolas:selecionar_foco'), {'escola': self.escola_a.pk})
        resposta = self.client.get(reverse('core:home'))
        self.assertContains(resposta, f'<option value="{self.escola_a.pk}" selected>')
        self.assertEqual(self.client.session[CHAVE_SESSAO], self.escola_a.pk)
        self.client.force_login(self.coord_a)
        resposta = self.client.get(reverse('core:home'))
        self.assertNotContains(resposta, 'id="menu-escola"')
        self.assertNotContains(resposta, 'id="desktop-escola"')

    def test_login_e_erro_de_acesso_tambem_tem_retorno(self):
        self.assertContains(self.client.get(reverse('usuarios:login')), 'id="voltar-pagina"', count=1)
        self.client.force_login(self.monitor)
        resposta = self.client.get(reverse('alunos:lista'))
        self.assertEqual(resposta.status_code, 403)
        self.assertContains(resposta, 'id="voltar-pagina"', count=1, status_code=403)
