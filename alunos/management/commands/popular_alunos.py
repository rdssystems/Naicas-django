"""
Gera atendidos FICTÍCIOS para desenvolvimento/demonstração, com as etapas 1 a 5
preenchidas (dados, endereço, responsáveis, família, contatos de emergência,
saúde e, via popular_anexos, PDFs fictícios dos documentos obrigatórios).

Parte dos atendidos é de irmãos que compartilham a mesma mãe, para exercitar o
reaproveitamento do responsável pelo CPF. Nunca rodar em produção.

Uso:
    python manage.py popular_alunos                     # 10 atendidos na única unidade
    python manage.py popular_alunos --quantidade 20 --escola naica-canaa --seed 42
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from alunos.models import Aluno
from escolas.models import EscolaNaica

from ...models import (
    Aluno, AlunoResponsavel, ContatoEmergencia, Endereco, FichaSaude, MembroFamiliar, Parentesco, Responsavel,
)

NOMES_FEMININOS = [
    'Ana', 'Beatriz', 'Camila', 'Larissa', 'Fernanda', 'Juliana', 'Mariana', 'Patrícia', 'Sabrina',
    'Vitória', 'Helena', 'Alice', 'Laura', 'Manuela', 'Valentina', 'Isadora', 'Lívia', 'Yasmin',
]
NOMES_MASCULINOS = [
    'Bruno', 'Carlos', 'Diego', 'Eduardo', 'Felipe', 'Gustavo', 'Henrique', 'João', 'Lucas',
    'Marcos', 'Rafael', 'Thiago', 'Arthur', 'Davi', 'Gabriel', 'Miguel', 'Pedro', 'Samuel',
]
SOBRENOMES = [
    'Almeida', 'Barbosa', 'Cardoso', 'Costa', 'Ferreira', 'Gomes', 'Lima', 'Martins', 'Moreira',
    'Nascimento', 'Oliveira', 'Pereira', 'Ribeiro', 'Rodrigues', 'Santos', 'Souza', 'Teixeira',
]
# Ruas fictícias em bairros reais de Uberlândia/MG (CEPs na faixa da cidade).
ENDERECOS = [
    ('38407000', 'Rua das Acácias', 'Canaã'),
    ('38407010', 'Rua dos Ipês', 'Canaã'),
    ('38407020', 'Rua Projetada Um', 'Canaã'),
    ('38412000', 'Avenida das Palmeiras', 'Jardim Holanda'),
    ('38410000', 'Rua das Orquídeas', 'Luizote de Freitas'),
    ('38411000', 'Rua dos Girassóis', 'Morumbi'),
    ('38408000', 'Rua das Hortênsias', 'Santa Mônica'),
    ('38405000', 'Rua dos Jasmins', 'Tibery'),
]
ESCOLAS = [
    'E.E. Professor Juvenília', 'E.M. Canaã', 'E.M. Professora Olga Del Fávero',
    'E.E. Bueno Brandão', 'E.M. Jardim Holanda',
]
OCUPACOES = ['Diarista', 'Auxiliar de produção', 'Vendedora', 'Pedreiro', 'Motorista', 'Cozinheira', 'Autônomo']
BENEFICIOS = ['Bolsa Família', 'BPC', 'Auxílio municipal']
PLANOS = ['Unimed', 'Plano municipal do servidor', 'Hapvida']
PROBLEMAS_SAUDE = ['Asma leve', 'Rinite alérgica', 'Diabetes tipo 1', 'Epilepsia controlada']
MEDICACOES = [('Ritalina 10mg', '1 ano', 'Perda de apetite'), ('Depakene', '2 anos', ''), ('Insulina NPH', '3 anos', '')]
ALERGIAS = ['Dipirona', 'Amendoim', 'Picada de abelha', 'Lactose', 'Penicilina']
DDD = '34'


def gerar_cpf(rng, usados):
    while True:
        digitos = [rng.randint(0, 9) for _ in range(9)]
        if len(set(digitos)) == 1:
            continue
        for tamanho in (9, 10):
            soma = sum(d * (tamanho + 1 - i) for i, d in enumerate(digitos))
            digitos.append((soma * 10) % 11 % 10)
        cpf = ''.join(map(str, digitos))
        if cpf not in usados and not Aluno.objects.filter(cpf=cpf).exists() \
                and not Responsavel.objects.filter(cpf=cpf).exists():
            usados.add(cpf)
            return cpf


def ano_escolar_pela_idade(idade):
    tabela = {6: 'EF1', 7: 'EF2', 8: 'EF3', 9: 'EF4', 10: 'EF5', 11: 'EF6', 12: 'EF7',
              13: 'EF8', 14: 'EF9', 15: 'EM1', 16: 'EM2', 17: 'EM3'}
    return tabela.get(idade, 'INFANTIL' if idade < 6 else 'EM3')


class Command(BaseCommand):
    help = 'Cria atendidos fictícios (cadastro completo) para desenvolvimento.'

    def add_arguments(self, parser):
        parser.add_argument('--quantidade', type=int, default=10)
        parser.add_argument('--escola', help='Slug da unidade (obrigatório se houver mais de uma).')
        parser.add_argument('--seed', type=int, help='Semente para gerar sempre os mesmos dados.')

    def handle(self, *args, quantidade, escola, seed, **options):
        if not settings.DEBUG:
            raise CommandError('Comando de desenvolvimento: só roda com DEBUG=True.')
        escola = self.resolver_escola(escola)
        self.rng = random.Random(seed)
        self.usados = set()
        self.hoje = date.today()

        criados = []
        with transaction.atomic():
            while len(criados) < quantidade:
                # ~1 em cada 3 famílias tem 2 irmãos (mesma mãe, mesmo endereço).
                filhos = 2 if quantidade - len(criados) >= 2 and self.rng.random() < 0.35 else 1
                criados += self.criar_familia(escola, filhos)
            # Etapa 5 é de outro app: chamado por nome, sem importar anexos.
            if apps.is_installed('anexos'):
                call_command('popular_anexos', aluno=[a.pk for a in criados], stdout=self.stdout)

        for aluno in criados:
            self.stdout.write(f'  {aluno.nome} ({aluno.get_ano_escolar_display()})')
        self.stdout.write(self.style.SUCCESS(f'{len(criados)} atendidos fictícios criados em {escola}.'))

    def resolver_escola(self, slug):
        if slug:
            try:
                return EscolaNaica.objects.get(slug=slug)
            except EscolaNaica.DoesNotExist:
                raise CommandError(f'Unidade "{slug}" não encontrada.')
        escolas = list(EscolaNaica.objects.all()[:2])
        if len(escolas) != 1:
            raise CommandError('Informe --escola <slug> (há zero ou mais de uma unidade).')
        return escolas[0]

    # --- geradores ---

    def nome(self, feminino, sobrenome):
        lista = NOMES_FEMININOS if feminino else NOMES_MASCULINOS
        return f'{self.rng.choice(lista)} {self.rng.choice(SOBRENOMES)} {sobrenome}'

    def celular(self):
        return f'{DDD}9{self.rng.randint(8000, 9999)}{self.rng.randint(1000, 9999)}'

    def data_nascimento(self, idade_min, idade_max):
        dias = self.rng.randint(idade_min * 365, idade_max * 365 + 364)
        return self.hoje - timedelta(days=dias)

    def criar_responsavel(self, feminino, sobrenome):
        trabalha = self.rng.random() < 0.7
        carteira = trabalha and self.rng.random() < 0.5
        beneficio = self.rng.random() < 0.4
        expedicao = self.data_nascimento(5, 15)
        return Responsavel.objects.create(
            cpf=gerar_cpf(self.rng, self.usados),
            nome=self.nome(feminino, sobrenome),
            data_nascimento=self.data_nascimento(25, 45),
            celular=self.celular(),
            email='' if self.rng.random() < 0.4 else f'responsavel{self.rng.randint(100, 999)}@exemplo.com',
            documento_numero=f'MG-{self.rng.randint(10, 99)}.{self.rng.randint(100, 999)}.{self.rng.randint(100, 999)}',
            documento_data_expedicao=expedicao,
            documento_orgao_expedidor='SSP',
            documento_uf='MG',
            trabalha=trabalha,
            carteira_assinada=carteira if trabalha else None,
            ctps_numero=str(self.rng.randint(1000000, 9999999)) if carteira else '',
            ctps_serie=f'{self.rng.randint(1, 999):03d}' if carteira else '',
            contribui_previdencia=carteira or (trabalha and self.rng.random() < 0.3),
            recebe_beneficio=beneficio,
            qual_beneficio=self.rng.choice(BENEFICIOS) if beneficio else '',
        )

    def renda(self, responsavel):
        if responsavel.carteira_assinada:
            return Decimal(self.rng.randrange(1518, 3200, 50))
        if responsavel.trabalha:
            return Decimal(self.rng.randrange(600, 1800, 50))
        return Decimal(0)

    def criar_ficha_saude(self, aluno):
        tipo = self.rng.choices(['SUS', 'PLANO', 'AMBOS'], weights=[7, 1, 2])[0]
        problema = self.rng.random() < 0.25
        medicacao = self.rng.choice(MEDICACOES) if self.rng.random() < 0.15 else None
        FichaSaude.objects.create(
            aluno=aluno,
            tipo_assistencia=tipo,
            plano_saude=self.rng.choice(PLANOS) if tipo != 'SUS' else '',
            possui_problema_saude=problema,
            problema_saude=self.rng.choice(PROBLEMAS_SAUDE) if problema else '',
            usa_medicacao_controlada=bool(medicacao),
            medicacao=medicacao[0] if medicacao else '',
            medicacao_ha_quanto_tempo=medicacao[1] if medicacao else '',
            medicacao_reacoes=medicacao[2] if medicacao else '',
            alergias=self.rng.choice(ALERGIAS) if self.rng.random() < 0.2 else '',
        )

    def criar_familia(self, escola, filhos):
        sobrenome = self.rng.choice(SOBRENOMES)
        cep, rua, bairro = self.rng.choice(ENDERECOS)
        numero = str(self.rng.randint(10, 999))
        mae = self.criar_responsavel(True, sobrenome)
        pai = self.criar_responsavel(False, sobrenome) if self.rng.random() < 0.5 else None
        avo = (self.nome(True, sobrenome), self.data_nascimento(55, 75)) if self.rng.random() < 0.3 else None

        alunos = []
        for _ in range(filhos):
            feminino = self.rng.random() < 0.5
            nascimento = self.data_nascimento(6, 16)
            idade = (self.hoje - nascimento).days // 365
            aluno = Aluno.objects.create(
                escola=escola,
                turno=self.rng.choice(Aluno.Turno.values),
                turma=self.rng.choice(Aluno.Turma.values),
                cpf=gerar_cpf(self.rng, self.usados),
                nome=self.nome(feminino, sobrenome),
                nome_mae=mae.nome,
                data_nascimento=nascimento,
                sexo='F' if feminino else 'M',
                naturalidade='Uberlândia/MG' if self.rng.random() < 0.8 else 'Araguari/MG',
                nis='' if self.rng.random() < 0.5 else str(self.rng.randint(10**10, 10**11 - 1)),
                nome_escola=self.rng.choice(ESCOLAS),
                ano_escolar=ano_escolar_pela_idade(idade),
            )
            Endereco.objects.create(
                aluno=aluno, cep=cep, logradouro=rua, numero=numero, bairro=bairro,
                complemento='', cidade='Uberlândia', estado='MG',
            )
            # Etapa 2: responsáveis (a mãe é a mesma pessoa para os irmãos).
            AlunoResponsavel.objects.create(aluno=aluno, responsavel=mae, grau_parentesco=Parentesco.MAE)
            if pai:
                AlunoResponsavel.objects.create(aluno=aluno, responsavel=pai, grau_parentesco=Parentesco.PAI)
            # Etapa 3: família (responsáveis ligados à linha) + contatos de emergência.
            for responsavel, parentesco in ((mae, Parentesco.MAE), (pai, Parentesco.PAI)):
                if responsavel:
                    MembroFamiliar.objects.create(
                        aluno=aluno, responsavel=responsavel, nome=responsavel.nome, parentesco=parentesco,
                        data_nascimento=responsavel.data_nascimento,
                        ocupacao=self.rng.choice(OCUPACOES) if responsavel.trabalha else 'Do lar',
                        renda_mensal=self.renda(responsavel),
                    )
            if avo:
                MembroFamiliar.objects.create(
                    aluno=aluno, nome=avo[0], parentesco=Parentesco.AVO, data_nascimento=avo[1],
                    ocupacao='Aposentada', renda_mensal=Decimal('1518.00'),
                )
            ContatoEmergencia.objects.create(
                aluno=aluno, nome=mae.nome, parentesco=Parentesco.MAE, celular=mae.celular,
            )
            segundo = (
                (pai.nome, Parentesco.PAI, pai.celular) if pai
                else (self.nome(True, sobrenome), self.rng.choice([Parentesco.TIO, Parentesco.AVO, Parentesco.VIZINHO]), self.celular())
            )
            ContatoEmergencia.objects.create(aluno=aluno, nome=segundo[0], parentesco=segundo[1], celular=segundo[2])
            self.criar_ficha_saude(aluno)
            alunos.append(aluno)

        # Irmãos também entram na composição familiar um do outro.
        for aluno in alunos:
            for irmao in alunos:
                if irmao != aluno:
                    MembroFamiliar.objects.create(
                        aluno=aluno, nome=irmao.nome, parentesco=Parentesco.IRMAO,
                        data_nascimento=irmao.data_nascimento, ocupacao='Estudante',
                    )
        return alunos
