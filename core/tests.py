from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase

from . import acesso

# Os testes de acesso com Profile (Diretor/Coordenador/Monitor) ficam em
# usuarios/tests.py, já que o core não depende do app usuarios.


class AnonimoTests(SimpleTestCase):
    def test_anonimo_nao_tem_papel(self):
        anonimo = AnonymousUser()
        self.assertIsNone(acesso.nivel_do_usuario(anonimo))
        self.assertIsNone(acesso.escola_do_usuario(anonimo))
        self.assertFalse(acesso.tem_acesso_ao_sistema(anonimo))
