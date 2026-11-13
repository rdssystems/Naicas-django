from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.acesso import NivelAcesso
from core.validators import cpf_valido
from escolas.models import EscolaNaica
from usuarios.models import Profile

from .forms import AlunoForm, ResponsavelForm
from .models import Aluno, AlunoResponsavel, ContatoEmergencia, Endereco, FichaSaude, MembroFamiliar, Responsavel


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


def criar_aluno(escola, base9, nome='Atendido', com_endereco=True):
    aluno = Aluno.objects.create(
        escola=escola, turno=Aluno.Turno.MANHA, turma=Aluno.Turma.A,
        cpf=gerar_cpf(base9), nome=nome, nome_mae='Mãe', data_nascimento=date(2015, 5, 10),
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
                reverse('alunos:etapa_familia', args=[self.aluno_a.pk]),
                reverse('alunos:etapa_saude', args=[self.aluno_a.pk]),
            ]
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 200, (user, url))


class OcorrenciaTests(BaseAlunosTestCase):
    def test_diretor_registra_ocorrencia(self):
        self.client.force_login(self.diretor)
        url = reverse('alunos:detalhe', args=[self.aluno_a.pk])

        response = self.client.post(url, {'descricao': 'Situação observada pela direção.'})

        self.assertRedirects(response, url)
        self.assertEqual(self.aluno_a.ocorrencias.get().autor, self.diretor)

    def test_coordenador_registra_e_consulta_ocorrencias_com_autor_e_data(self):
        self.client.force_login(self.coord_a)
        url = reverse('alunos:detalhe', args=[self.aluno_a.pk])
        response = self.client.post(url, {'descricao': 'Atendido passou mal durante a atividade.'})

        self.assertRedirects(response, url)
        ocorrencia = self.aluno_a.ocorrencias.get()
        self.assertEqual(ocorrencia.autor, self.coord_a)
        self.assertEqual(ocorrencia.data, date.today())
        self.assertEqual(ocorrencia.descricao, 'Atendido passou mal durante a atividade.')

        response = self.client.get(url)
        self.assertContains(response, 'Atendido passou mal durante a atividade.')
        self.assertContains(response, self.coord_a.get_full_name() or self.coord_a.username)

    def test_historico_mostra_registros_em_ordem_cronologica(self):
        from .models import Ocorrencia

        antiga = Ocorrencia.objects.create(aluno=self.aluno_a, descricao='Primeira situação.', autor=self.coord_a)
        recente = Ocorrencia.objects.create(aluno=self.aluno_a, descricao='Segunda situação.', autor=self.coord_a)
        self.client.force_login(self.diretor)
        response = self.client.get(reverse('alunos:detalhe', args=[self.aluno_a.pk]))

        itens = list(response.context['ocorrencias'])
        self.assertEqual(itens, [antiga, recente])

    def test_coordenador_nao_registra_ocorrencia_para_aluno_de_outra_unidade(self):
        self.client.force_login(self.coord_a)
        url = reverse('alunos:detalhe', args=[self.aluno_b.pk])
        self.assertEqual(self.client.post(url, {'descricao': 'Tentativa.'}).status_code, 404)
        self.assertFalse(self.aluno_b.ocorrencias.exists())

    def test_monitor_nao_acessa_registro_de_ocorrencias(self):
        self.client.force_login(self.monitor)
        url = reverse('alunos:detalhe', args=[self.aluno_a.pk])
        self.assertEqual(self.client.post(url, {'descricao': 'Tentativa.'}).status_code, 403)
        self.assertFalse(self.aluno_a.ocorrencias.exists())

    def test_descricao_e_obrigatoria(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(reverse('alunos:detalhe', args=[self.aluno_a.pk]), {'descricao': '  '})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.aluno_a.ocorrencias.exists())
        self.assertContains(response, 'Este campo é obrigatório.')


class EtapaDadosTests(BaseAlunosTestCase):
    def dados(self, cpf, **kwargs):
        base = {
            'cpf': formatar(cpf), 'nome': 'Carla', 'nome_mae': 'Joana', 'data_nascimento': '2014-02-03',
            'turno': Aluno.Turno.MANHA, 'turma': Aluno.Turma.A,
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
        self.assertEqual((aluno.turno, aluno.turma), (Aluno.Turno.MANHA, Aluno.Turma.A))
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

    def test_novo_cadastro_exige_turno_e_turma(self):
        dados = self.dados(gerar_cpf(300000005), turno='', turma='')
        form = AlunoForm(data=dados, user=self.coord_a)
        self.assertFalse(form.is_valid())
        self.assertIn('turno', form.errors)
        self.assertIn('turma', form.errors)

    def test_alunos_antigos_sem_classificacao_aparecem_como_pendentes(self):
        Aluno.objects.filter(pk=self.aluno_a.pk).update(turno=None, turma=None)
        self.client.force_login(self.coord_a)
        response = self.client.get(reverse('alunos:lista'), {'classificacao': 'pendente'})
        self.assertEqual(list(response.context['alunos']), [self.aluno_a])
        self.assertContains(response, 'Pendente')

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

    def test_adiciona_responsavel_novo_e_conclui_etapa(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(self.url(self.aluno_a), self.dados(gerar_cpf(400000001)))
        self.assertRedirects(response, self.url(self.aluno_a))
        vinculo = self.aluno_a.responsaveis_vinculos.get()
        self.assertEqual(vinculo.grau_parentesco, 'MAE')
        etapa2 = Aluno.objects.get(pk=self.aluno_a.pk).etapas()[1]
        self.assertTrue(etapa2[3])

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


class EtapaFamiliaTests(BaseAlunosTestCase):
    def url(self, aluno):
        return reverse('alunos:etapa_familia', args=[aluno.pk])

    def management(self, prefixo, total, inicial=0):
        return {
            f'{prefixo}-TOTAL_FORMS': str(total), f'{prefixo}-INITIAL_FORMS': str(inicial),
            f'{prefixo}-MIN_NUM_FORMS': '0', f'{prefixo}-MAX_NUM_FORMS': '1000',
        }

    def dados(self, membros=(), contatos=()):
        dados = {**self.management('membros', len(membros)), **self.management('contatos', len(contatos))}
        for i, membro in enumerate(membros):
            dados.update({f'membros-{i}-{campo}': valor for campo, valor in membro.items()})
        for i, contato in enumerate(contatos):
            dados.update({f'contatos-{i}-{campo}': valor for campo, valor in contato.items()})
        return dados

    CONTATOS = (
        {'nome': 'Tia Ana', 'parentesco': 'TIO', 'celular': '81911112222'},
        {'nome': 'Avô Zé', 'parentesco': 'AVO', 'celular': '81933334444'},
    )

    def test_salva_membros_e_contatos_e_soma_renda(self):
        membros = (
            {'nome': 'Joana', 'parentesco': 'MAE', 'ocupacao': 'Diarista', 'renda_mensal': '1.518,50'},
            {'nome': 'Pedro', 'parentesco': 'IRMAO', 'renda_mensal': ''},
            {'nome': 'Carlos', 'parentesco': 'PAI', 'renda_mensal': '800'},
        )
        self.client.force_login(self.coord_a)
        response = self.client.post(self.url(self.aluno_a), self.dados(membros, self.CONTATOS))
        self.assertRedirects(response, reverse('alunos:detalhe', args=[self.aluno_a.pk]))
        aluno = Aluno.objects.get(pk=self.aluno_a.pk)
        self.assertEqual(aluno.membros_familia.count(), 3)
        self.assertEqual(str(aluno.renda_familiar), '2318.50')
        self.assertEqual(aluno.contatos_emergencia.count(), 2)
        self.assertTrue(aluno.etapas()[2][3])

    def test_familia_e_opcional_mas_exige_2_contatos(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(self.url(self.aluno_a), self.dados(contatos=self.CONTATOS[:1]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['contatos_formset'].non_form_errors())
        self.assertFalse(ContatoEmergencia.objects.filter(aluno=self.aluno_a).exists())

    def test_primeira_visita_mostra_2_contatos_em_branco(self):
        self.client.force_login(self.coord_a)
        response = self.client.get(self.url(self.aluno_a))
        self.assertEqual(len(response.context['contatos_formset'].forms), 2)
        self.assertEqual(len(response.context['membros_formset'].forms), 0)

    def test_remover_contato_abaixo_do_minimo_e_barrado(self):
        c1 = ContatoEmergencia.objects.create(aluno=self.aluno_a, **self.CONTATOS[0])
        c2 = ContatoEmergencia.objects.create(aluno=self.aluno_a, **self.CONTATOS[1])
        contatos = (
            {'id': c1.pk, **self.CONTATOS[0], 'DELETE': 'on'},
            {'id': c2.pk, **self.CONTATOS[1]},
        )
        dados = self.dados(contatos=contatos)
        dados['contatos-INITIAL_FORMS'] = '2'
        self.client.force_login(self.coord_a)
        response = self.client.post(self.url(self.aluno_a), dados)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.aluno_a.contatos_emergencia.count(), 2)

    def test_remover_membro(self):
        membro = MembroFamiliar.objects.create(aluno=self.aluno_a, nome='Ex', parentesco='TIO')
        dados = self.dados(
            membros=({'id': membro.pk, 'nome': 'Ex', 'parentesco': 'TIO', 'DELETE': 'on'},),
            contatos=self.CONTATOS,
        )
        dados['membros-INITIAL_FORMS'] = '1'
        self.client.force_login(self.coord_a)
        self.client.post(self.url(self.aluno_a), dados)
        self.assertFalse(MembroFamiliar.objects.filter(pk=membro.pk).exists())

    def test_renda_negativa_e_rejeitada(self):
        membros = ({'nome': 'X', 'parentesco': 'MAE', 'renda_mensal': '-10'},)
        self.client.force_login(self.coord_a)
        response = self.client.post(self.url(self.aluno_a), self.dados(membros, self.CONTATOS))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.aluno_a.membros_familia.exists())

    def test_etapas_1_a_4_concluidas(self):
        # O selo "Cadastro completo" também depende dos anexos (ver anexos/tests.py).
        AlunoResponsavel.objects.create(aluno=self.aluno_a, responsavel=criar_responsavel(500000001), grau_parentesco='MAE')
        for contato in self.CONTATOS:
            ContatoEmergencia.objects.create(aluno=self.aluno_a, **contato)
        self.assertFalse(Aluno.objects.get(pk=self.aluno_a.pk).etapas()[3][3])  # falta saúde
        FichaSaude.objects.create(
            aluno=self.aluno_a, tipo_assistencia='SUS', possui_problema_saude=False, usa_medicacao_controlada=False,
        )
        concluidas = [e[3] for e in Aluno.objects.get(pk=self.aluno_a.pk).etapas()[:4]]
        self.assertEqual(concluidas, [True, True, True, True])

    def test_permissoes(self):
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.get(self.url(self.aluno_a)).status_code, 403)
        self.client.force_login(self.coord_a)
        self.assertEqual(self.client.get(self.url(self.aluno_b)).status_code, 404)
        response = self.client.post(self.url(self.aluno_b), self.dados(contatos=self.CONTATOS))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.aluno_b.contatos_emergencia.exists())


class PreenchimentoResponsaveisTests(BaseAlunosTestCase):
    """Responsáveis da etapa 2 entram pré-preenchidos na composição familiar."""

    def setUp(self):
        self.mae = criar_responsavel(600000001, 'Joana Mãe')
        self.pai = criar_responsavel(600000002, 'Carlos Pai')
        AlunoResponsavel.objects.create(aluno=self.aluno_a, responsavel=self.mae, grau_parentesco='MAE')
        AlunoResponsavel.objects.create(aluno=self.aluno_a, responsavel=self.pai, grau_parentesco='PAI')
        self.url = reverse('alunos:etapa_familia', args=[self.aluno_a.pk])
        self.client.force_login(self.coord_a)

    def linhas_iniciais(self, response):
        return [(f.initial.get('nome'), f.initial.get('parentesco')) for f in response.context['membros_formset'].forms]

    def test_primeira_visita_traz_os_responsaveis(self):
        response = self.client.get(self.url)
        self.assertEqual(self.linhas_iniciais(response), [('Joana Mãe', 'MAE'), ('Carlos Pai', 'PAI')])
        self.assertContains(response, 'Incluímos os responsáveis do atendido')

    def test_depois_de_salva_nao_reinsere_quem_foi_removido(self):
        MembroFamiliar.objects.create(aluno=self.aluno_a, responsavel=self.mae, nome='Joana Mãe', parentesco='MAE')
        ContatoEmergencia.objects.create(aluno=self.aluno_a, nome='A', parentesco='TIO', celular='1')
        response = self.client.get(self.url)
        self.assertEqual(self.linhas_iniciais(response), [('Joana Mãe', 'MAE')])  # só a salva
        self.assertEqual([v.responsavel for v in response.context['responsaveis_faltando']], [self.pai])

    def test_incluir_responsaveis_que_faltam(self):
        MembroFamiliar.objects.create(aluno=self.aluno_a, responsavel=self.mae, nome='Joana Mãe', parentesco='MAE')
        response = self.client.get(self.url, {'incluir_responsaveis': '1'})
        self.assertEqual(self.linhas_iniciais(response), [('Joana Mãe', 'MAE'), ('Carlos Pai', 'PAI')])

    def test_membro_digitado_a_mao_com_mesmo_nome_nao_duplica(self):
        MembroFamiliar.objects.create(aluno=self.aluno_a, nome='  joana mãe ', parentesco='MAE')
        faltando = [v.responsavel for v in Aluno.objects.get(pk=self.aluno_a.pk).vinculos_fora_da_familia()]
        self.assertEqual(faltando, [self.pai])

    def test_salvar_pre_preenchidos_guarda_o_vinculo_e_remove_o_pai(self):
        membros = (
            {'responsavel': self.mae.pk, 'nome': 'Joana Mãe', 'parentesco': 'MAE', 'renda_mensal': '1.200,00'},
            {'responsavel': self.pai.pk, 'nome': 'Carlos Pai', 'parentesco': 'PAI', 'DELETE': 'on'},
        )
        self.client.post(self.url, self.dados(membros, EtapaFamiliaTests.CONTATOS))
        salvo = MembroFamiliar.objects.get(aluno=self.aluno_a)
        self.assertEqual(salvo.responsavel, self.mae)
        self.assertEqual(MembroFamiliar.objects.filter(aluno=self.aluno_a).count(), 1)

    def test_vinculo_com_responsavel_de_outro_aluno_e_recusado(self):
        estranho = criar_responsavel(600000003, 'Estranho')
        AlunoResponsavel.objects.create(aluno=self.aluno_b, responsavel=estranho, grau_parentesco='PAI')
        membros = ({'responsavel': estranho.pk, 'nome': 'Estranho', 'parentesco': 'PAI'},)
        response = self.client.post(self.url, self.dados(membros, EtapaFamiliaTests.CONTATOS))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MembroFamiliar.objects.filter(aluno=self.aluno_a).exists())

    def test_parentesco_fora_da_lista_e_recusado(self):
        membros = ({'nome': 'X', 'parentesco': 'Mãe'},)
        response = self.client.post(self.url, self.dados(membros, EtapaFamiliaTests.CONTATOS))
        self.assertEqual(response.status_code, 200)
        self.assertIn('parentesco', response.context['membros_formset'].forms[0].errors)

    # Reaproveita os helpers de montagem do POST.
    management = EtapaFamiliaTests.management
    dados = EtapaFamiliaTests.dados


class PopularAlunosCommandTests(BaseAlunosTestCase):
    def test_gera_alunos_completos_e_validos(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings

        import shutil
        import tempfile

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        with override_settings(DEBUG=True, MEDIA_ROOT=media):
            call_command('popular_alunos', quantidade=6, escola='naica-norte', seed=1, stdout=StringIO())
        novos = Aluno.objects.filter(escola=self.escola_b).exclude(pk=self.aluno_b.pk)
        self.assertEqual(novos.count(), 6)
        for aluno in novos:
            self.assertTrue(aluno.cadastro_completo, aluno)
            aluno.full_clean()

    def test_recusa_sem_debug(self):
        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command('popular_alunos', escola='naica-norte')


class EtapaSaudeTests(BaseAlunosTestCase):
    def url(self, aluno):
        return reverse('alunos:etapa_saude', args=[aluno.pk])

    def dados(self, **kwargs):
        base = {
            'tipo_assistencia': 'SUS', 'plano_saude': '',
            'possui_problema_saude': 'False', 'problema_saude': '',
            'usa_medicacao_controlada': 'False', 'medicacao': '', 'medicacao_ha_quanto_tempo': '',
            'medicacao_reacoes': '', 'alergias': '',
        }
        base.update(kwargs)
        return base

    def test_salva_ficha_e_conclui_etapa(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(self.url(self.aluno_a), self.dados(
            usa_medicacao_controlada='True', medicacao='Ritalina', medicacao_ha_quanto_tempo='1 ano',
            alergias='Dipirona',
        ))
        self.assertRedirects(response, reverse('alunos:detalhe', args=[self.aluno_a.pk]))
        ficha = FichaSaude.objects.get(aluno=self.aluno_a)
        self.assertEqual(ficha.medicacao, 'Ritalina')
        self.assertEqual(ficha.atualizado_por, self.coord_a)
        self.assertTrue(Aluno.objects.get(pk=self.aluno_a.pk).etapas()[3][3])

    def test_edicao_atualiza_a_mesma_ficha(self):
        self.client.force_login(self.coord_a)
        self.client.post(self.url(self.aluno_a), self.dados())
        self.client.post(self.url(self.aluno_a), self.dados(alergias='Amendoim'))
        self.assertEqual(FichaSaude.objects.filter(aluno=self.aluno_a).count(), 1)
        self.assertEqual(FichaSaude.objects.get(aluno=self.aluno_a).alergias, 'Amendoim')

    def test_campos_condicionais(self):
        self.client.force_login(self.coord_a)
        casos = [
            ({'tipo_assistencia': 'PLANO'}, 'plano_saude'),
            ({'tipo_assistencia': 'AMBOS'}, 'plano_saude'),
            ({'possui_problema_saude': 'True'}, 'problema_saude'),
            ({'usa_medicacao_controlada': 'True'}, 'medicacao'),
        ]
        for extra, campo in casos:
            response = self.client.post(self.url(self.aluno_a), self.dados(**extra))
            self.assertEqual(response.status_code, 200, extra)
            self.assertIn(campo, response.context['form'].errors, extra)
        self.assertFalse(FichaSaude.objects.filter(aluno=self.aluno_a).exists())

    def test_sim_nao_obrigatorios(self):
        self.client.force_login(self.coord_a)
        response = self.client.post(
            self.url(self.aluno_a), self.dados(possui_problema_saude='', usa_medicacao_controlada='')
        )
        self.assertEqual(set(response.context['form'].errors), {'possui_problema_saude', 'usa_medicacao_controlada'})

    def test_respostas_que_deixam_de_valer_sao_limpas(self):
        self.client.force_login(self.coord_a)
        self.client.post(self.url(self.aluno_a), self.dados(
            tipo_assistencia='SUS', plano_saude='Unimed', usa_medicacao_controlada='False', medicacao='X',
        ))
        ficha = FichaSaude.objects.get(aluno=self.aluno_a)
        self.assertEqual((ficha.plano_saude, ficha.medicacao), ('', ''))

    def test_lgpd_monitor_nao_acessa_nem_pela_url(self):
        FichaSaude.objects.create(
            aluno=self.aluno_a, tipo_assistencia='SUS', possui_problema_saude=True, problema_saude='Segredo',
            usa_medicacao_controlada=False,
        )
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.get(self.url(self.aluno_a)).status_code, 403)
        self.assertEqual(self.client.post(self.url(self.aluno_a), self.dados()).status_code, 403)
        self.assertEqual(FichaSaude.objects.get(aluno=self.aluno_a).problema_saude, 'Segredo')

    def test_coordenador_de_outra_unidade_nao_ve(self):
        self.client.force_login(self.coord_b)
        self.assertEqual(self.client.get(self.url(self.aluno_a)).status_code, 404)

    def test_resumo_mostra_saude_para_quem_pode(self):
        FichaSaude.objects.create(
            aluno=self.aluno_a, tipo_assistencia='SUS', possui_problema_saude=True, problema_saude='Asma leve',
            usa_medicacao_controlada=False, alergias='Dipirona',
        )
        self.client.force_login(self.coord_a)
        response = self.client.get(reverse('alunos:detalhe', args=[self.aluno_a.pk]))
        self.assertContains(response, 'Dipirona')
        self.assertContains(response, 'Asma leve')

    def test_regra_de_papel_centralizada(self):
        from core import acesso
        self.assertTrue(acesso.pode_ver_saude_completa(self.diretor))
        self.assertTrue(acesso.pode_ver_saude_completa(self.coord_a))
        self.assertFalse(acesso.pode_ver_saude_completa(self.monitor))
        self.assertFalse(acesso.pode_ver_saude_emergencia(self.monitor))  # até a decisão de LGPD


class PopularDemoCommandTests(TestCase):
    """Comando de demonstração (Isaque): roda com o código atual e não duplica a carga."""

    def test_cria_carga_em_uma_unidade_e_recusa_duplicar(self):
        import shutil
        import tempfile
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings

        from frequencia.models import ChamadaGeral
        from matriculas.models import Matricula
        from oficinas.models import AtividadeCronograma, Oficina

        unidade = EscolaNaica.objects.order_by('pk').first()
        EscolaNaica.objects.exclude(pk=unidade.pk).delete()  # só uma unidade: teste rápido
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        with override_settings(DEBUG=True, MEDIA_ROOT=media):
            call_command('popular_demo', seed=1, stdout=StringIO())
            total_alunos = Aluno.objects.filter(escola=unidade).count()
            self.assertGreaterEqual(total_alunos, 35)
            self.assertLessEqual(total_alunos, 45)
            self.assertEqual(AtividadeCronograma.objects.filter(escola=unidade, dados_legados__demo=True).count(), 5)
            total_matriculas = Matricula.objects.filter(escola=unidade).count()
            self.assertEqual(total_matriculas, 0)
            self.assertFalse(AtividadeCronograma.objects.filter(escola=unidade, turmas=[]).exists())
            self.assertFalse(Aluno.objects.filter(escola=unidade, turno__isnull=True).exists())
            self.assertFalse(Aluno.objects.filter(escola=unidade, turma__isnull=True).exists())
            self.assertTrue(ChamadaGeral.objects.exists())
            call_command('popular_demo', seed=1, stdout=StringIO())
            self.assertEqual(Aluno.objects.filter(escola=unidade).count(), total_alunos)
