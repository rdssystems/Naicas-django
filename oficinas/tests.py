from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.acesso import NivelAcesso
from escolas.models import EscolaNaica
from usuarios.models import Profile

from .forms import OficinaForm, TipoOficinaForm
from .models import Oficina, TipoOficina


def criar_usuario(username, nivel, escola=None, **extra):
    user = User.objects.create_user(username=username, password='x', first_name=username, **extra)
    Profile.objects.create(user=user, nivel_acesso=nivel, escola=escola)
    return user


def criar_oficina(tipo, nome='Oficina', **kwargs):
    dados = dict(
        tipo_oficina=tipo, nome=nome, carga_horaria=40, vagas=20,
        data_inicio=date(2026, 3, 1), data_fim=date(2026, 6, 30),
        turno=Oficina.Turno.MANHA, horario=time(8), horario_fim=time(10),
        dias_semana=[0, 2],
    )
    dados.update(kwargs)
    return Oficina.objects.create(**dados)


class BaseOficinasTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.escola_a = EscolaNaica.objects.create(nome='Naica Centro')
        cls.escola_b = EscolaNaica.objects.create(nome='Naica Norte')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord_a = criar_usuario('coord_a', NivelAcesso.COORDENADOR, cls.escola_a)
        cls.coord_b = criar_usuario('coord_b', NivelAcesso.COORDENADOR, cls.escola_b)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.outro_monitor = criar_usuario('outro_monitor', NivelAcesso.MONITOR)

        cls.tipo_a = TipoOficina.objects.create(escola=cls.escola_a, nome='Dança')
        cls.tipo_b = TipoOficina.objects.create(escola=cls.escola_b, nome='Música')
        # Monitor global designado em oficinas de DUAS unidades diferentes.
        cls.oficina_a = criar_oficina(cls.tipo_a, 'Dança Manhã')
        cls.oficina_b = criar_oficina(cls.tipo_b, 'Violão')
        cls.oficina_b_sem_monitor = criar_oficina(cls.tipo_b, 'Teclado')
        cls.oficina_a.monitores.add(cls.monitor)
        cls.oficina_b.monitores.add(cls.monitor)


class ModeloTests(BaseOficinasTestCase):
    def test_escola_vem_do_tipo(self):
        self.assertEqual(self.oficina_a.escola, self.escola_a)
        self.assertEqual(self.oficina_b.escola, self.escola_b)

    def test_mesmo_nome_de_tipo_em_unidades_diferentes(self):
        TipoOficina.objects.create(escola=self.escola_b, nome='Dança')

    def test_validacoes_de_data_horario_e_dias(self):
        oficina = Oficina(
            tipo_oficina=self.tipo_a, nome='X', carga_horaria=1, vagas=1,
            data_inicio=date(2026, 6, 1), data_fim=date(2026, 5, 1),
            turno=Oficina.Turno.TARDE, horario=time(14), horario_fim=time(13), dias_semana=[],
        )
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError) as ctx:
            oficina.full_clean(exclude=['escola'])
        self.assertEqual(
            set(ctx.exception.message_dict), {'data_fim', 'horario_fim', 'dias_semana'}
        )

    def test_dias_semana_display(self):
        self.assertEqual(self.oficina_a.dias_semana_display, 'Seg, Qua')


class VisibilidadeTests(BaseOficinasTestCase):
    def nomes_na_lista(self, user, **params):
        self.client.force_login(user)
        response = self.client.get(reverse('oficinas:lista'), params)
        self.assertEqual(response.status_code, 200)
        return {o.nome for o in response.context['oficinas']}

    def test_diretor_ve_todas(self):
        self.assertEqual(self.nomes_na_lista(self.diretor), {'Dança Manhã', 'Violão', 'Teclado'})

    def test_coordenador_ve_so_a_propria_unidade(self):
        self.assertEqual(self.nomes_na_lista(self.coord_b), {'Violão', 'Teclado'})

    def test_monitor_global_ve_so_as_designadas_em_varias_unidades(self):
        self.assertEqual(self.nomes_na_lista(self.monitor), {'Dança Manhã', 'Violão'})

    def test_monitor_sem_designacao_nao_ve_nada(self):
        self.assertEqual(self.nomes_na_lista(self.outro_monitor), set())

    def test_arquivada_fora_da_lista_padrao(self):
        criar_oficina(self.tipo_a, 'Antiga', status=Oficina.Status.ARQUIVADO)
        self.assertNotIn('Antiga', self.nomes_na_lista(self.diretor))
        self.assertIn('Antiga', self.nomes_na_lista(self.diretor, status='todas'))

    def test_detalhe(self):
        casos = [
            (self.monitor, self.oficina_b, 200),
            (self.monitor, self.oficina_b_sem_monitor, 403),
            (self.coord_a, self.oficina_a, 200),
            (self.coord_a, self.oficina_b, 403),
            (self.diretor, self.oficina_b, 200),
        ]
        for user, oficina, esperado in casos:
            self.client.force_login(user)
            response = self.client.get(reverse('oficinas:detalhe', args=[oficina.pk]))
            self.assertEqual(response.status_code, esperado, (user, oficina))


class EdicaoPermissaoTests(BaseOficinasTestCase):
    def test_telas_de_cadastro_renderizam(self):
        for user in (self.diretor, self.coord_a):
            self.client.force_login(user)
            urls = [
                reverse('oficinas:criar'),
                reverse('oficinas:editar', args=[self.oficina_a.pk]),
                reverse('oficinas:tipos'),
                reverse('oficinas:tipo_criar'),
                reverse('oficinas:tipo_editar', args=[self.tipo_a.pk]),
            ]
            for url in urls:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, (user, url))
        # Checkboxes dos dias com a classe do Bootstrap.
        response = self.client.get(reverse('oficinas:criar'))
        self.assertContains(response, 'class="form-check-input"', count=7)  # 7 dias (monitores agora na escala)


    def test_monitor_nao_cria_nem_edita(self):
        self.client.force_login(self.monitor)
        urls = [
            reverse('oficinas:criar'),
            reverse('oficinas:editar', args=[self.oficina_a.pk]),
            reverse('oficinas:tipos'),
            reverse('oficinas:tipo_criar'),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_coordenador_nao_edita_oficina_de_outra_unidade(self):
        self.client.force_login(self.coord_a)
        response = self.client.get(reverse('oficinas:editar', args=[self.oficina_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_coordenador_nao_edita_tipo_de_outra_unidade(self):
        self.client.force_login(self.coord_a)
        response = self.client.get(reverse('oficinas:tipo_editar', args=[self.tipo_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_coordenador_nao_exclui_tipo_de_outra_unidade(self):
        tipo = TipoOficina.objects.create(escola=self.escola_b, nome='Sem uso')
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('oficinas:tipo_excluir', args=[tipo.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(TipoOficina.objects.filter(pk=tipo.pk).exists())


class TipoOficinaFormTests(BaseOficinasTestCase):
    def test_coordenador_cria_tipo_na_propria_unidade(self):
        form = TipoOficinaForm(data={'nome': 'Teatro', 'cor': '#ff0000'}, user=self.coord_a)
        self.assertNotIn('escola', form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().escola, self.escola_a)

    def test_coordenador_nome_duplicado_na_unidade(self):
        form = TipoOficinaForm(data={'nome': 'dança', 'cor': '#ff0000'}, user=self.coord_a)
        self.assertFalse(form.is_valid())
        self.assertIn('nome', form.errors)

    def test_diretor_nao_muda_unidade_de_tipo_em_uso(self):
        form = TipoOficinaForm(instance=self.tipo_a, user=self.diretor)
        self.assertTrue(form.fields['escola'].disabled)

    def test_tipo_em_uso_nao_e_excluido(self):
        self.client.force_login(self.coord_a)
        self.client.post(reverse('oficinas:tipo_excluir', args=[self.tipo_a.pk]))
        self.assertTrue(TipoOficina.objects.filter(pk=self.tipo_a.pk).exists())

    def test_tipo_sem_uso_e_excluido(self):
        tipo = TipoOficina.objects.create(escola=self.escola_a, nome='Sem uso')
        self.client.force_login(self.coord_a)
        self.client.post(reverse('oficinas:tipo_excluir', args=[tipo.pk]))
        self.assertFalse(TipoOficina.objects.filter(pk=tipo.pk).exists())


class OficinaFormTests(BaseOficinasTestCase):
    def dados(self, **kwargs):
        base = {
            'tipo_oficina': self.tipo_a.pk, 'nome': 'Nova', 'carga_horaria': 30, 'vagas': 15,
            'data_inicio': '2026-03-01', 'data_fim': '2026-07-01', 'dias_semana': ['1', '3'],
            'turno': Oficina.Turno.TARDE, 'horario': '14:00', 'horario_fim': '16:00',
            'status': Oficina.Status.ABERTA,
            'nome_monitor': '', 'telefone_monitor': '',
        }
        base.update(kwargs)
        return base

    def test_coordenador_so_ve_tipos_da_unidade(self):
        form = OficinaForm(user=self.coord_a)
        self.assertEqual(list(form.fields['tipo_oficina'].queryset), [self.tipo_a])

    def test_coordenador_nao_usa_tipo_de_outra_unidade(self):
        form = OficinaForm(data=self.dados(tipo_oficina=self.tipo_b.pk), user=self.coord_a)
        self.assertFalse(form.is_valid())
        self.assertIn('tipo_oficina', form.errors)

    def test_coordenador_cria_oficina_sem_campo_de_monitores(self):
        self.assertNotIn('monitores', OficinaForm(user=self.coord_a).fields)
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('oficinas:criar'), self.dados())
        oficina = Oficina.objects.get(nome='Nova')
        self.assertRedirects(response, reverse('oficinas:detalhe', args=[oficina.pk]))
        self.assertEqual((oficina.escola, oficina.dias_semana), (self.escola_a, [1, 3]))

    def test_edicao_nao_troca_unidade(self):
        tipo_a2 = TipoOficina.objects.create(escola=self.escola_a, nome='Teatro')
        form = OficinaForm(instance=self.oficina_a, user=self.diretor)
        self.assertEqual(set(form.fields['tipo_oficina'].queryset), {self.tipo_a, tipo_a2})


class NavegacaoTiposTests(BaseOficinasTestCase):
    def test_tipos_de_oficina_saiu_de_configuracoes_e_virou_botao(self):
        self.client.force_login(self.coord_a)
        lista = self.client.get(reverse('oficinas:lista'))
        self.assertContains(lista, f'href="{reverse("oficinas:tipos")}" class="btn')
        self.assertNotContains(lista, '>Configurações<')  # Coordenador não tem mais o menu
        self.client.force_login(self.diretor)
        home = self.client.get(reverse('core:home'))
        self.assertContains(home, '>Configurações<')
        self.assertNotContains(home, f'class="dropdown-item" href="{reverse("oficinas:tipos")}"')


class DesignacaoDiasTests(BaseOficinasTestCase):
    def test_oficina_que_perde_dia_ajusta_as_designacoes(self):
        from .models import Designacao
        # oficina_a: seg/qua. monitor só na quarta; outro_monitor em todos os dias (vazio).
        Designacao.objects.filter(oficina=self.oficina_a, monitor=self.monitor).update(dias_semana=[2])
        Designacao.objects.create(oficina=self.oficina_a, monitor=self.outro_monitor)
        self.oficina_a.dias_semana = [0]  # deixou de ter quarta
        self.oficina_a.save()
        self.assertFalse(Designacao.objects.filter(oficina=self.oficina_a, monitor=self.monitor).exists())
        restante = Designacao.objects.get(oficina=self.oficina_a, monitor=self.outro_monitor)
        self.assertEqual((restante.dias_semana, restante.dias_efetivos), ([], [0]))

    def test_detalhe_mostra_dias_da_escala(self):
        from .models import Designacao
        Designacao.objects.filter(oficina=self.oficina_a, monitor=self.monitor).update(dias_semana=[2])
        self.client.force_login(self.coord_a)
        response = self.client.get(reverse('oficinas:detalhe', args=[self.oficina_a.pk]))
        self.assertContains(response, '· Qua')
