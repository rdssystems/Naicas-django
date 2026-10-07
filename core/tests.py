from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase

from . import acesso

# Os testes de acesso com Profile (Diretor/Coordenador/Monitor) ficam em
# usuarios/tests.py, já que o core não depende do app usuarios.


class AnonimoTests(SimpleTestCase):
    def test_anonimo_nao_tem_papel(self):
        anonimo = AnonymousUser()
        self.assertIsNone(acesso.nivel_do_usuario(anonimo))
        self.assertIsNone(acesso.escola_do_usuario(anonimo))
        self.assertFalse(acesso.tem_acesso_ao_sistema(anonimo))


class FaviconTests(TestCase):
    def test_favicon_ico_redireciona_para_o_estatico(self):
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].endswith('core/favicon.ico'))

    def test_base_declara_os_icones(self):
        response = self.client.get('/usuarios/login/')
        self.assertContains(response, 'core/favicon.svg')
        self.assertContains(response, 'core/apple-touch-icon.png')
