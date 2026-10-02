from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views import View

from core import acesso
from core.acesso import NivelAcesso
from core.mixins import MonitorRequiredMixin
from escolas.models import EscolaNaica

from .forms import UsuarioForm
from .models import Profile

SENHA = 'Naicas@2026forte'


def criar_usuario(username, nivel=None, escola=None, **extra):
    user = User.objects.create_user(username=username, password=SENHA, first_name=username, **extra)
    if nivel:
        Profile.objects.create(user=user, nivel_acesso=nivel, escola=escola)
    return user


class BaseAcessoTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.escola_a = EscolaNaica.objects.create(nome='Naica Centro')
        cls.escola_b = EscolaNaica.objects.create(nome='Naica Norte')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord_a = criar_usuario('coord_a', NivelAcesso.COORDENADOR, cls.escola_a)
        cls.coord_b = criar_usuario('coord_b', NivelAcesso.COORDENADOR, cls.escola_b)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.sem_perfil = criar_usuario('sem_perfil')
        cls.superuser = User.objects.create_superuser('root', password=SENHA)


class ProfileConstraintTests(BaseAcessoTestCase):
    def test_coordenador_sem_escola_e_barrado_no_banco(self):
        user = criar_usuario('x')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Profile.objects.create(user=user, nivel_acesso=NivelAcesso.COORDENADOR, escola=None)

    def test_monitor_com_escola_e_barrado_no_banco(self):
        user = criar_usuario('x')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Profile.objects.create(user=user, nivel_acesso=NivelAcesso.MONITOR, escola=self.escola_a)

    def test_diretor_com_escola_e_barrado_no_banco(self):
        user = criar_usuario('x')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Profile.objects.create(user=user, nivel_acesso=NivelAcesso.DIRETOR, escola=self.escola_a)

    def test_clean_explica_o_erro(self):
        profile = Profile(user=criar_usuario('x'), nivel_acesso=NivelAcesso.COORDENADOR)
        with self.assertRaises(ValidationError) as ctx:
            profile.full_clean()
        self.assertIn('escola', ctx.exception.message_dict)

    def test_grupo_acompanha_o_nivel(self):
        self.assertEqual(list(self.monitor.groups.values_list('name', flat=True)), ['Monitor'])
        profile = self.monitor.profile
        profile.nivel_acesso = NivelAcesso.DIRETOR
        profile.save()
        self.assertEqual(list(self.monitor.groups.values_list('name', flat=True)), ['Diretor'])

    def test_grupos_de_papel_existem(self):
        self.assertEqual(
            set(Group.objects.values_list('name', flat=True)),
            {'Diretor', 'Coordenador', 'Monitor'},
        )


class RegrasDeAcessoTests(BaseAcessoTestCase):
    def test_monitor_sem_escola_nao_e_diretor(self):
        # Regra crítica do Naicas: escola=None não significa acesso de rede.
        self.assertIsNone(acesso.escola_do_usuario(self.monitor))
        self.assertFalse(acesso.is_diretor(self.monitor))
        self.assertTrue(acesso.is_monitor(self.monitor))

    def test_superuser_sem_perfil_e_diretor(self):
        self.assertTrue(acesso.is_diretor(self.superuser))

    def test_usuario_sem_perfil_nao_tem_acesso(self):
        self.assertFalse(acesso.tem_acesso_ao_sistema(self.sem_perfil))

    def test_filtrar_por_escola(self):
        qs = Profile.objects.all()
        self.assertEqual(acesso.filtrar_por_escola(self.diretor, qs).count(), qs.count())
        self.assertEqual(
            list(acesso.filtrar_por_escola(self.coord_a, qs)), [self.coord_a.profile]
        )
        self.assertFalse(acesso.filtrar_por_escola(self.monitor, qs).exists())
        self.assertFalse(acesso.filtrar_por_escola(self.sem_perfil, qs).exists())

    def test_pode_gerenciar_escola(self):
        self.assertTrue(acesso.pode_gerenciar_escola(self.diretor, self.escola_b.pk))
        self.assertTrue(acesso.pode_gerenciar_escola(self.coord_a, self.escola_a.pk))
        self.assertFalse(acesso.pode_gerenciar_escola(self.coord_a, self.escola_b.pk))
        self.assertFalse(acesso.pode_gerenciar_escola(self.monitor, self.escola_a.pk))


class OficinaFalsa:
    """Substituto de Oficina até o app oficinas existir (Etapa 2)."""

    def __init__(self, escola, monitores):
        self.escola_id = escola.pk
        self.monitores = User.objects.filter(pk__in=[m.pk for m in monitores])


class MonitorRequiredMixinTests(BaseAcessoTestCase):
    def setUp(self):
        self.oficina_a = OficinaFalsa(self.escola_a, monitores=[self.monitor])
        self.oficina_b = OficinaFalsa(self.escola_b, monitores=[])
        self.factory = RequestFactory()

    def chamar(self, user, oficina):
        class ChamadaView(MonitorRequiredMixin, View):
            def get_oficina(self):
                return oficina

            def get(self, request):
                from django.http import HttpResponse
                return HttpResponse('ok')

        request = self.factory.get('/')
        request.user = user
        return ChamadaView.as_view()(request)

    def test_monitor_designado_acessa_oficina_de_qualquer_unidade(self):
        self.assertEqual(self.chamar(self.monitor, self.oficina_a).status_code, 200)

    def test_monitor_nao_designado_e_barrado(self):
        with self.assertRaises(PermissionDenied):
            self.chamar(self.monitor, self.oficina_b)

    def test_coordenador_so_na_propria_unidade(self):
        self.assertEqual(self.chamar(self.coord_a, self.oficina_a).status_code, 200)
        with self.assertRaises(PermissionDenied):
            self.chamar(self.coord_a, self.oficina_b)

    def test_diretor_acessa_qualquer_oficina(self):
        self.assertEqual(self.chamar(self.diretor, self.oficina_b).status_code, 200)


class LoginTests(BaseAcessoTestCase):
    def test_login_por_username(self):
        response = self.client.post(
            reverse('usuarios:login'), {'username': 'coord_a', 'password': SENHA}
        )
        self.assertRedirects(response, reverse('core:home'))

    def test_home_exige_login(self):
        response = self.client.get(reverse('core:home'))
        self.assertRedirects(response, f"{reverse('usuarios:login')}?next=/")

    def test_usuario_sem_perfil_recebe_403(self):
        self.client.force_login(self.sem_perfil)
        self.assertEqual(self.client.get(reverse('core:home')).status_code, 403)

    def test_cada_papel_acessa_o_painel(self):
        for user in (self.diretor, self.coord_a, self.monitor, self.superuser):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('core:home')).status_code, 200, user)

    def test_logout_por_post(self):
        self.client.force_login(self.monitor)
        response = self.client.post(reverse('usuarios:logout'))
        self.assertRedirects(response, reverse('usuarios:login'))


class GestaoDeUsuariosPermissaoTests(BaseAcessoTestCase):
    URLS = ['usuarios:lista', 'usuarios:criar']

    def test_so_diretor_gerencia_usuarios(self):
        for user in (self.coord_a, self.monitor, self.sem_perfil):
            self.client.force_login(user)
            for nome in self.URLS:
                self.assertEqual(self.client.get(reverse(nome)).status_code, 403, (user, nome))
            url_editar = reverse('usuarios:editar', args=[self.monitor.pk])
            self.assertEqual(self.client.get(url_editar).status_code, 403, user)

    def test_diretor_acessa(self):
        self.client.force_login(self.diretor)
        for nome in self.URLS:
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    def test_coordenador_nao_desativa_usuario(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('usuarios:alternar_ativo', args=[self.monitor.pk]))
        self.assertEqual(response.status_code, 403)
        self.monitor.refresh_from_db()
        self.assertTrue(self.monitor.is_active)


class UsuarioFormTests(BaseAcessoTestCase):
    def dados(self, **kwargs):
        base = {
            'username': 'novo',
            'first_name': 'Novo',
            'last_name': 'Usuário',
            'email': '',
            'nivel_acesso': NivelAcesso.MONITOR,
            'escola': '',
            'senha': SENHA,
            'senha_confirmacao': SENHA,
        }
        base.update(kwargs)
        return base

    def test_diretor_cria_monitor_global(self):
        self.client.force_login(self.diretor)
        response = self.client.post(reverse('usuarios:criar'), self.dados())
        self.assertRedirects(response, reverse('usuarios:lista'))
        novo = User.objects.get(username='novo')
        self.assertEqual(novo.profile.nivel_acesso, NivelAcesso.MONITOR)
        self.assertIsNone(novo.profile.escola)
        self.assertTrue(novo.check_password(SENHA))

    def test_monitor_ignora_escola_enviada(self):
        form = UsuarioForm(data=self.dados(escola=self.escola_a.pk))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().profile.escola)

    def test_coordenador_exige_escola(self):
        form = UsuarioForm(data=self.dados(nivel_acesso=NivelAcesso.COORDENADOR))
        self.assertFalse(form.is_valid())
        self.assertIn('escola', form.errors)

    def test_coordenador_com_escola(self):
        form = UsuarioForm(
            data=self.dados(nivel_acesso=NivelAcesso.COORDENADOR, escola=self.escola_b.pk)
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().profile.escola, self.escola_b)

    def test_senhas_diferentes(self):
        form = UsuarioForm(data=self.dados(senha_confirmacao='outra-coisa-123'))
        self.assertFalse(form.is_valid())
        self.assertIn('senha_confirmacao', form.errors)

    def test_senha_fraca(self):
        form = UsuarioForm(data=self.dados(senha='123', senha_confirmacao='123'))
        self.assertFalse(form.is_valid())
        self.assertIn('senha', form.errors)

    def test_edicao_sem_senha_mantem_a_atual(self):
        form = UsuarioForm(
            data=self.dados(username='monitor', senha='', senha_confirmacao=''),
            instance=self.monitor,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.monitor.refresh_from_db()
        self.assertTrue(self.monitor.check_password(SENHA))

    def test_diretor_nao_rebaixa_a_si_mesmo(self):
        form = UsuarioForm(
            data=self.dados(username='diretor', nivel_acesso=NivelAcesso.MONITOR, senha='', senha_confirmacao=''),
            instance=self.diretor,
            usuario_logado=self.diretor,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('nivel_acesso', form.errors)

    def test_coordenador_rebaixado_deixa_de_ser_responsavel_da_escola(self):
        self.escola_a.coordenador_user = self.coord_a
        self.escola_a.save()
        form = UsuarioForm(
            data=self.dados(username='coord_a', senha='', senha_confirmacao=''),
            instance=self.coord_a,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.escola_a.refresh_from_db()
        self.assertIsNone(self.escola_a.coordenador_user)

    def test_diretor_nao_desativa_a_si_mesmo(self):
        self.client.force_login(self.diretor)
        self.client.post(reverse('usuarios:alternar_ativo', args=[self.diretor.pk]))
        self.diretor.refresh_from_db()
        self.assertTrue(self.diretor.is_active)

    def test_diretor_desativa_e_reativa(self):
        self.client.force_login(self.diretor)
        url = reverse('usuarios:alternar_ativo', args=[self.monitor.pk])
        self.client.post(url)
        self.monitor.refresh_from_db()
        self.assertFalse(self.monitor.is_active)
        self.client.post(url)
        self.monitor.refresh_from_db()
        self.assertTrue(self.monitor.is_active)
