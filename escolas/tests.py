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


class FocoNaUnidadeTests(TestCase):
    """Diretor "entra" numa unidade pela barra do topo ou fica na visão geral."""

    @classmethod
    def setUpTestData(cls):
        from oficinas.models import TipoOficina
        from oficinas.tests import criar_oficina
        from alunos.tests import criar_aluno

        cls.canaa = EscolaNaica.objects.create(nome='Naica Teste')
        cls.norte = EscolaNaica.objects.create(nome='Naica Norte')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord = criar_usuario('coord', NivelAcesso.COORDENADOR, cls.canaa)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.oficina_canaa = criar_oficina(TipoOficina.objects.create(escola=cls.canaa, nome='Dança'), 'Dança')
        cls.oficina_norte = criar_oficina(TipoOficina.objects.create(escola=cls.norte, nome='Música'), 'Violão')
        cls.aluno_canaa = criar_aluno(cls.canaa, 950000001, 'Ana')
        cls.aluno_norte = criar_aluno(cls.norte, 950000002, 'Bruno')

    def entrar(self, escola, user=None):
        self.client.force_login(user or self.diretor)
        return self.client.post(reverse('escolas:selecionar_foco'), {'escola': escola.pk if escola else ''})

    def nomes(self, url, chave):
        return {str(o) for o in self.client.get(url).context[chave]}

    def test_visao_geral_mostra_tudo_e_marca_naicas(self):
        self.client.force_login(self.diretor)
        self.assertEqual(self.nomes(reverse('oficinas:lista'), 'oficinas'), {'Dança', 'Violão'})
        self.assertEqual(self.nomes(reverse('alunos:lista'), 'alunos'), {'Ana', 'Bruno'})
        self.assertContains(self.client.get(reverse('core:home')), '<span class="fita">Naicas</span>')

    def test_dentro_da_unidade_filtra_e_mostra_o_nome_na_barra(self):
        self.assertRedirects(self.entrar(self.canaa), reverse('core:home'))
        self.assertEqual(self.nomes(reverse('oficinas:lista'), 'oficinas'), {'Dança'})
        self.assertEqual(self.nomes(reverse('alunos:lista'), 'alunos'), {'Ana'})
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, '<span class="fita">Naica Teste</span>')
        self.assertContains(response, 'Você está dentro da unidade')

    def test_continua_diretor_dentro_da_unidade(self):
        self.entrar(self.canaa)
        self.assertEqual(self.client.get(reverse('usuarios:lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('escolas:lista')).status_code, 200)

    def test_voltar_a_visao_geral(self):
        self.entrar(self.canaa)
        self.entrar(None)
        self.assertEqual(self.nomes(reverse('oficinas:lista'), 'oficinas'), {'Dança', 'Violão'})

    def test_unidade_nova_aparece_no_seletor_automaticamente(self):
        self.client.force_login(self.diretor)
        EscolaNaica.objects.create(nome='Naica Recém-criada')
        response = self.client.get(reverse('core:home'))
        self.assertIn('Naica Recém-criada', {e.nome for e in response.context['unidades_para_foco']})
        self.assertContains(response, 'Naica Recém-criada')

    def test_coordenador_nao_troca_de_unidade(self):
        response = self.entrar(self.norte, user=self.coord)
        self.assertEqual(response.status_code, 403)
        # Mesmo forjando a sessão, o foco é ignorado para quem não é Diretor (regra de ouro).
        from escolas.foco import CHAVE_SESSAO
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = self.norte.pk
        sessao.save()
        self.assertEqual(self.nomes(reverse('oficinas:lista'), 'oficinas'), {'Dança'})
        self.assertContains(self.client.get(reverse('core:home')), '<span class="fita">Naica Teste</span>')

    def test_unidade_inexistente_ou_invalida(self):
        self.client.force_login(self.diretor)
        url = reverse('escolas:selecionar_foco')
        self.assertEqual(self.client.post(url, {'escola': '99999'}).status_code, 404)
        self.assertEqual(self.client.post(url, {'escola': 'abc'}).status_code, 404)

    def test_foco_de_unidade_apagada_volta_para_visao_geral(self):
        temporaria = EscolaNaica.objects.create(nome='Temporária')
        self.entrar(temporaria)
        temporaria.delete()
        self.assertEqual(self.nomes(reverse('oficinas:lista'), 'oficinas'), {'Dança', 'Violão'})

    def test_novo_aluno_vem_com_a_unidade_em_foco(self):
        self.entrar(self.norte)
        response = self.client.get(reverse('alunos:criar'))
        self.assertEqual(response.context['form'].initial.get('escola'), self.norte.pk)

    def test_so_admin_e_diretor_entram_em_unidades(self):
        superuser = User.objects.create_superuser('admin', password='x')  # sem Profile: tratado como Diretor
        self.assertRedirects(self.entrar(self.norte, user=superuser), reverse('core:home'))
        self.assertEqual(self.nomes(reverse('oficinas:lista'), 'oficinas'), {'Violão'})
        for user in (self.coord, self.monitor):
            self.assertEqual(self.entrar(self.norte, user=user).status_code, 403, user)
            response = self.client.get(reverse('core:home'))
            self.assertNotIn('unidades_para_foco', response.context)
            self.assertNotContains(response, 'Visão geral da rede')


class UnidadesUberlandiaTests(TestCase):
    def test_migracao_cria_as_10_unidades(self):
        unidades = EscolaNaica.objects.filter(email__endswith='@uberlandia.mg.gov.br')
        self.assertEqual(unidades.count(), 10)
        tibery = unidades.get(nome='Naica Tibery')
        self.assertEqual(tibery.telefone, '(34) 3213-5998')
        self.assertEqual(tibery.slug, 'naica-tibery')
        self.assertIn('Avenida Europa, 175', tibery.endereco)
