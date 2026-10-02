from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.acesso import NivelAcesso
from core.validators import cpf_valido
from escolas.models import EscolaNaica
from usuarios.models import Profile

from .forms import AlunoForm, ResponsavelForm
from .models import Aluno, AlunoResponsavel, Endereco, Responsavel


def gerar_cpf(base9):
    """CPF válido a partir de 9 dígitos (calcula os verificadores)."""
    digitos = [int(d) for d in f'{base9:09d}']
    for tamanho in (9, 10):
        soma = sum(d * (tamanho + 1 - i) for i, d in enumerate(digitos))
        digitos.append((soma * 10) % 11 % 10)
    return ''.join(map(str, digitos))


def formatar(cpf):
    return f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}'


def criar_usuario(username, nivel, escola=None):
    user = User.objects.create_user(username=username, password='x', first_name=username)
    Profile.objects.create(user=user, nivel_acesso=nivel, escola=escola)
    return user


def criar_aluno(escola, base9, nome='Aluno', com_endereco=True):
    aluno = Aluno.objects.create(
        escola=escola, cpf=gerar_cpf(base9), nome=nome, nome_mae='Mãe', data_nascimento=date(2015, 5, 10),
        sexo='F', naturalidade='Recife/PE', nome_escola='EM Teste', ano_escolar='EF5',
    )
    if com_endereco:
        Endereco.objects.create(
            aluno=aluno, cep='50000000', logradouro='Rua A', bairro='Centro', cidade='Recife', estado='PE',
        )
    return aluno


def criar_responsavel(base9, nome='Maria'):
    return Responsavel.objects.create(
        cpf=gerar_cpf(base9), nome=nome, data_nascimento=date(1985, 1, 1), celular='81999990000',
        documento_numero='123', documento_data_expedicao=date(2005, 1, 1),
        documento_orgao_expedidor='SDS', documento_uf='PE', trabalha=False, recebe_beneficio=False,
    )


class ValidadorCPFTests(TestCase):
    def test_cpf(self):
        self.assertTrue(cpf_valido(gerar_cpf(123456789)))
        self.assertTrue(cpf_valido(formatar(gerar_cpf(123456789))))
        self.assertFalse(cpf_valido('12345678900'))
        self.assertFalse(cpf_valido('11111111111'))
        self.assertFalse(cpf_valido('123'))


class BaseAlunosTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.escola_a = EscolaNaica.objects.create(nome='Naica Centro')
        cls.escola_b = EscolaNaica.objects.create(nome='Naica Norte')
        cls.diretor = criar_usuario('diretor', NivelAcesso.DIRETOR)
        cls.coord_a = criar_usuario('coord_a', NivelAcesso.COORDENADOR, cls.escola_a)
        cls.coord_b = criar_usuario('coord_b', NivelAcesso.COORDENADOR, cls.escola_b)
        cls.monitor = criar_usuario('monitor', NivelAcesso.MONITOR)
        cls.aluno_a = criar_aluno(cls.escola_a, 100000001, 'Ana')
        cls.aluno_b = criar_aluno(cls.escola_b, 100000002, 'Bruno')


class VisibilidadeTests(BaseAlunosTestCase):
    def test_queryset_por_papel(self):
        self.assertEqual(set(Aluno.objects.visiveis_para(self.diretor)), {self.aluno_a, self.aluno_b})
        self.assertEqual(list(Aluno.objects.visiveis_para(self.coord_a)), [self.aluno_a])
        self.assertFalse(Aluno.objects.visiveis_para(self.monitor).exists())

    def test_lista(self):
        self.client.force_login(self.coord_b)
        response = self.client.get(reverse('alunos:lista'))
        self.assertEqual(list(response.context['alunos']), [self.aluno_b])

    def test_busca_por_cpf_formatado(self):
        self.client.force_login(self.diretor)
        response = self.client.get(reverse('alunos:lista'), {'q': formatar(self.aluno_a.cpf)[:11]})
        self.assertEqual(list(response.context['alunos']), [self.aluno_a])

    def test_monitor_nao_acessa_cadastro(self):
        self.client.force_login(self.monitor)
        urls = [
            reverse('alunos:lista'), reverse('alunos:criar'),
            reverse('alunos:detalhe', args=[self.aluno_a.pk]),
            reverse('alunos:etapa_responsaveis', args=[self.aluno_a.pk]),
            reverse('alunos:buscar_responsavel'),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_coordenador_nao_acessa_aluno_de_outra_unidade(self):
        self.client.force_login(self.coord_a)
        urls = [
            reverse('alunos:detalhe', args=[self.aluno_b.pk]),
            reverse('alunos:etapa_dados', args=[self.aluno_b.pk]),
            reverse('alunos:etapa_responsaveis', args=[self.aluno_b.pk]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_telas_renderizam(self):
        AlunoResponsavel.objects.create(aluno=self.aluno_a, responsavel=criar_responsavel(200000001), grau_parentesco='MAE')
        vinculo = self.aluno_a.responsaveis_vinculos.get()
        for user in (self.diretor, self.coord_a):
            self.client.force_login(user)
            urls = [
                reverse('alunos:lista'), reverse('alunos:criar'),
                reverse('alunos:detalhe', args=[self.aluno_a.pk]),
                reverse('alunos:etapa_dados', args=[self.aluno_a.pk]),
                reverse('alunos:etapa_responsaveis', args=[self.aluno_a.pk]),
                reverse('alunos:responsavel_editar', args=[self.aluno_a.pk, vinculo.pk]),
            ]
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 200, (user, url))


class EtapaDadosTests(BaseAlunosTestCase):
    def dados(self, cpf, **kwargs):
        base = {
            'cpf': formatar(cpf), 'nome': 'Carla', 'nome_mae': 'Joana', 'data_nascimento': '2014-02-03',
            'sexo': 'F', 'naturalidade': 'Olinda/PE', 'nis': '', 'nome_escola': 'EM X', 'ano_escolar': 'EF6',
            'end-cep': '50.000-000', 'end-logradouro': 'Rua B', 'end-numero': '', 'end-complemento': '',
            'end-bairro': 'Boa Vista', 'end-cidade': 'Recife', 'end-estado': 'PE',
        }
        base.update(kwargs)
        return base

    def test_coordenador_cadastra_na_propria_unidade(self):
        self.client.force_login(self.coord_a)
        cpf = gerar_cpf(300000001)
        response = self.client.post(reverse('alunos:criar'), self.dados(cpf))
        aluno = Aluno.objects.get(cpf=cpf)
        self.assertRedirects(response, reverse('alunos:etapa_responsaveis', args=[aluno.pk]))
        self.assertEqual(aluno.escola, self.escola_a)
        self.assertEqual(aluno.criado_por, self.coord_a)
        self.assertEqual(aluno.endereco.cep, '50000000')
        self.assertFalse(aluno.cadastro_completo)  # falta responsável

    def test_diretor_escolhe_unidade(self):
        self.client.force_login(self.diretor)
        cpf = gerar_cpf(300000002)
        self.client.post(reverse('alunos:criar'), self.dados(cpf, escola=self.escola_b.pk))
        self.assertEqual(Aluno.objects.get(cpf=cpf).escola, self.escola_b)

    def test_endereco_incompleto_nao_salva_nada(self):
        self.client.force_login(self.coord_a)
        cpf = gerar_cpf(300000003)
        response = self.client.post(reverse('alunos:criar'), self.dados(cpf, **{'end-bairro': '', 'end-cidade': ''}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Aluno.objects.filter(cpf=cpf).exists())
        self.assertIn('bairro', response.context['endereco_form'].errors)

    def test_cpf_invalido(self):
        form = AlunoForm(data=self.dados('12345678900'), user=self.coord_a)
        self.assertFalse(form.is_valid())
        self.assertIn('cpf', form.errors)

    def test_cpf_de_outra_unidade_avisa_sem_mostrar(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('alunos:criar'), self.dados(self.aluno_b.cpf))
        self.assertEqual(response.status_code, 200)
        erro = response.context['form'].errors['cpf'][0]
        self.assertIn('Naica Norte', erro)
        self.assertIsNone(response.context['aluno_existente_visivel'])
        self.assertNotContains(response, self.aluno_b.nome)

    def test_cpf_da_propria_unidade_mostra_link(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('alunos:criar'), self.dados(self.aluno_a.cpf))
        self.assertEqual(response.context['aluno_existente_visivel'], self.aluno_a)

    def test_coordenador_edita_sem_trocar_unidade(self):
        self.client.force_login(self.coord_a)
        dados = self.dados(self.aluno_a.cpf, nome='Ana Paula', escola=self.escola_b.pk)
        response = self.client.post(reverse('alunos:etapa_dados', args=[self.aluno_a.pk]), dados)
        self.assertRedirects(response, reverse('alunos:detalhe', args=[self.aluno_a.pk]))
        self.aluno_a.refresh_from_db()
        self.assertEqual(self.aluno_a.nome, 'Ana Paula')
        self.assertEqual(self.aluno_a.escola, self.escola_a)


class EtapaResponsaveisTests(BaseAlunosTestCase):
    def dados(self, cpf, **kwargs):
        base = {
            'cpf': formatar(cpf), 'nome': 'Joana Silva', 'grau_parentesco': 'MAE', 'data_nascimento': '1988-04-04',
            'celular': '81988887777', 'email': '', 'documento_numero': '998877',
            'documento_data_expedicao': '2006-01-01', 'documento_orgao_expedidor': 'SDS', 'documento_uf': 'PE',
            'trabalha': 'False', 'carteira_assinada': '', 'ctps_numero': '', 'ctps_serie': '',
            'contribui_previdencia': '', 'recebe_beneficio': 'False', 'qual_beneficio': '',
        }
        base.update(kwargs)
        return base

    def url(self, aluno):
        return reverse('alunos:etapa_responsaveis', args=[aluno.pk])

    def test_adiciona_responsavel_novo_e_completa_cadastro(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(self.url(self.aluno_a), self.dados(gerar_cpf(400000001)))
        self.assertRedirects(response, self.url(self.aluno_a))
        vinculo = self.aluno_a.responsaveis_vinculos.get()
        self.assertEqual(vinculo.grau_parentesco, 'MAE')
        self.assertTrue(Aluno.objects.get(pk=self.aluno_a.pk).cadastro_completo)

    def test_reaproveita_responsavel_pelo_cpf_entre_unidades(self):
        # Mesmo responsável (mãe de irmãos em unidades diferentes): não duplica.
        responsavel = criar_responsavel(400000002, 'Maria Antiga')
        AlunoResponsavel.objects.create(aluno=self.aluno_b, responsavel=responsavel, grau_parentesco='MAE')
        self.client.force_login(self.coord_a)
        self.client.post(self.url(self.aluno_a), self.dados(responsavel.cpf, nome='Maria Atualizada'))
        self.assertEqual(Responsavel.objects.filter(cpf=responsavel.cpf).count(), 1)
        responsavel.refresh_from_db()
        self.assertEqual(responsavel.nome, 'Maria Atualizada')
        self.assertEqual(responsavel.alunos_vinculos.count(), 2)

    def test_nao_vincula_duas_vezes(self):
        responsavel = criar_responsavel(400000003)
        AlunoResponsavel.objects.create(aluno=self.aluno_a, responsavel=responsavel, grau_parentesco='MAE')
        form = ResponsavelForm(self.dados(responsavel.cpf), instance=responsavel, aluno=self.aluno_a)
        self.assertFalse(form.is_valid())

    def test_campos_condicionais(self):
        cpf = gerar_cpf(400000004)
        casos = [
            ({'trabalha': 'True'}, 'carteira_assinada'),
            ({'trabalha': 'True', 'carteira_assinada': 'True'}, 'ctps_numero'),
            ({'recebe_beneficio': 'True'}, 'qual_beneficio'),
        ]
        for extra, campo in casos:
            form = ResponsavelForm(self.dados(cpf, **extra), aluno=self.aluno_a)
            self.assertFalse(form.is_valid(), extra)
            self.assertIn(campo, form.errors, extra)

    def test_respostas_que_deixam_de_valer_sao_limpas(self):
        cpf = gerar_cpf(400000005)
        form = ResponsavelForm(
            self.dados(cpf, trabalha='False', carteira_assinada='True', ctps_numero='1', ctps_serie='2'),
            aluno=self.aluno_a,
        )
        self.assertTrue(form.is_valid(), form.errors)
        responsavel = form.save()
        self.assertIsNone(responsavel.carteira_assinada)
        self.assertEqual(responsavel.ctps_numero, '')

    def test_busca_por_cpf(self):
        responsavel = criar_responsavel(400000006, 'Rita')
        self.client.force_login(self.coord_b)
        url = reverse('alunos:buscar_responsavel')
        dados = self.client.get(url, {'cpf': formatar(responsavel.cpf)}).json()
        self.assertTrue(dados['encontrado'])
        self.assertEqual(dados['dados']['nome'], 'Rita')
        self.assertEqual(dados['dados']['trabalha'], 'False')
        self.assertEqual(dados['dados']['data_nascimento'], '1985-01-01')
        self.assertFalse(self.client.get(url, {'cpf': gerar_cpf(999999999)}).json()['encontrado'])

    def test_editar_e_remover_vinculo(self):
        responsavel = criar_responsavel(400000007)
        vinculo = AlunoResponsavel.objects.create(aluno=self.aluno_a, responsavel=responsavel, grau_parentesco='MAE')
        self.client.force_login(self.coord_a)
        url_editar = reverse('alunos:responsavel_editar', args=[self.aluno_a.pk, vinculo.pk])
        self.client.post(url_editar, self.dados(responsavel.cpf, grau_parentesco='AVO'))
        vinculo.refresh_from_db()
        self.assertEqual(vinculo.grau_parentesco, 'AVO')

        self.client.post(reverse('alunos:responsavel_remover', args=[self.aluno_a.pk, vinculo.pk]))
        self.assertFalse(AlunoResponsavel.objects.filter(pk=vinculo.pk).exists())
        self.assertTrue(Responsavel.objects.filter(pk=responsavel.pk).exists())

    def test_coordenador_nao_mexe_em_vinculo_de_aluno_de_outra_unidade(self):
        responsavel = criar_responsavel(400000008)
        vinculo = AlunoResponsavel.objects.create(aluno=self.aluno_b, responsavel=responsavel, grau_parentesco='MAE')
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('alunos:responsavel_remover', args=[self.aluno_b.pk, vinculo.pk]))
        self.assertEqual(response.status_code, 404)
        # Vínculo de outro aluno pela URL do próprio aluno também não.
        response = self.client.post(reverse('alunos:responsavel_remover', args=[self.aluno_a.pk, vinculo.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(AlunoResponsavel.objects.filter(pk=vinculo.pk).exists())
