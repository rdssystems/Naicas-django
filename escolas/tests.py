from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.acesso import NivelAcesso
from usuarios.models import Profile

from .forms import EscolaNaicaForm
from .models import EscolaNaica


def criar_usuario(username, nivel, escola=None):
    user = User.objects.create_user(username=username, password='x')
    Profile.objects.create(user=user, nivel_acesso=nivel, escola=escola)
    return user


class EscolaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.escola = EscolaNaica.objects.create(nome='Naica Centro')
        cls.outra = EscolaNaica.objects.create(nome='Naica Sul')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord = criar_usuario('coord', NivelAcesso.COORDENADOR, cls.escola)
        cls.coord_outra = criar_usuario('coord_outra', NivelAcesso.COORDENADOR, cls.outra)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)

    def test_slug_unico_gerado(self):
        self.assertEqual(self.escola.slug, 'naica-centro')
        homonima = EscolaNaica(nome='Naica  Centro')  # mesmo slug, nome diferente
        homonima.save()
        self.assertEqual(homonima.slug, 'naica-centro-2')

    def test_so_diretor_acessa_telas_de_unidade(self):
        urls = [
            reverse('escolas:lista'),
            reverse('escolas:criar'),
            reverse('escolas:editar', args=[self.escola.pk]),
        ]
        for user in (self.coord, self.monitor):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, (user, url))
        self.client.force_login(self.diretor)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_diretor_cadastra_unidade(self):
        self.client.force_login(self.diretor)
        response = self.client.post(reverse('escolas:criar'), {'nome': 'Naica Leste'})
        self.assertRedirects(response, reverse('escolas:lista'))
        self.assertTrue(EscolaNaica.objects.filter(nome='Naica Leste').exists())

    def test_responsavel_so_entre_coordenadores_da_unidade(self):
        form = EscolaNaicaForm(instance=self.escola)
        self.assertEqual(list(form.fields['coordenador_user'].queryset), [self.coord])

    def test_responsavel_de_outra_unidade_e_rejeitado(self):
        form = EscolaNaicaForm(
            data={'nome': self.escola.nome, 'coordenador_user': self.coord_outra.pk},
            instance=self.escola,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('coordenador_user', form.errors)
