"""Cria ou randomiza os dados fictícios para demonstrar o Naicas.

Uso: python manage.py popular_demo [--seed 2026]
Gera 35–45 atendidos, cinco oficinas por turma e chamadas gerais por
unidade. Sem --seed, os números e as presenças variam a cada execução.
Só funciona com DEBUG=True; altera somente dados de demonstração.
"""

import random
import secrets
import string
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.acesso import NivelAcesso
from alunos.models import Aluno
from escolas.models import EscolaNaica
from frequencia.models import ChamadaGeral

from oficinas.models import AtividadeCronograma, Oficina
from usuarios.models import Profile


OFICINAS_DEMO = [
    ('Esporte e Movimento', '#2e7a4c'),
    ('Artes e Criatividade', '#c8471f'),
    ('Tecnologia', '#2b3a8c'),
    ('Música', '#f2b705'),
    ('Apoio Escolar', '#4a64c8'),
]
NOMES_INSTRUTORES = [
    ('Mariana', 'Lopes'), ('Rafael', 'Alves'), ('Camila', 'Santos'),
    ('Bruno', 'Oliveira'), ('Juliana', 'Costa'), ('Felipe', 'Souza'),
    ('Beatriz', 'Ribeiro'), ('Lucas', 'Martins'), ('Larissa', 'Gomes'),
    ('Gabriel', 'Pereira'),
]


def alunos_demo(escola, user):
    # A carga demo nÃ£o adota nem reclassifica alunos reais referenciados por engano.
    qs = Aluno.objects.filter(escola=escola, criado_por=user).order_by('pk')
    return list(qs)


def gerar_senha_temporaria():
    alfabeto = string.ascii_letters + string.digits + '!@#$%'
    caracteres = [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase),
                  secrets.choice(string.digits), secrets.choice('!@#$%')]
    caracteres.extend(secrets.choice(alfabeto) for _ in range(12))
    secrets.SystemRandom().shuffle(caracteres)
    return ''.join(caracteres)


class Command(BaseCommand):
    help = 'Cria ou randomiza dados fictícios para demonstração (somente desenvolvimento).'

    def add_arguments(self, parser):
        parser.add_argument('--seed', type=int, help='Semente opcional para reproduzir a mesma carga.')

    def handle(self, *args, seed, **options):
        if not settings.DEBUG:
            raise CommandError('Comando de demonstração: só roda com DEBUG=True.')
        escolas = list(EscolaNaica.objects.order_by('pk'))
        if not escolas:
            raise CommandError('Nenhuma unidade cadastrada. Rode as migrações primeiro.')

        rng = random.Random(seed)
        hoje = timezone.localdate()
        resumo = []
        novas_contas = []

        with transaction.atomic():
            for indice_escola, escola in enumerate(escolas):
                sufixo = escola.slug.replace('-', '_')
                username = f'demo_instrutor_{sufixo}'
                primeiro_nome, sobrenome = NOMES_INSTRUTORES[indice_escola % len(NOMES_INSTRUTORES)]
                user, usuario_novo = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'first_name': primeiro_nome,
                        'last_name': sobrenome,
                        'email': f'{username}@example.invalid',
                    },
                )
                if usuario_novo:
                    senha = gerar_senha_temporaria()
                    user.set_password(senha)
                    user.save(update_fields=['password'])
                    novas_contas.append((escola.nome, username, senha))
                perfil, perfil_novo = Profile.objects.get_or_create(
                    user=user,
                    defaults={'nivel_acesso': NivelAcesso.MONITOR, 'escola': None},
                )
                if not perfil_novo and (
                    perfil.nivel_acesso != NivelAcesso.MONITOR or perfil.escola_id is not None
                ):
                    raise CommandError(f'A conta {username} já existe com outro perfil; nada foi alterado.')
                if not user.is_active:
                    user.is_active = True
                    user.save(update_fields=['is_active'])

                oficinas = []
                turnos = ['MANHA'] * 3 + ['TARDE'] * 2
                horarios = [(8, 0), (9, 30), (11, 0), (13, 0), (14, 30)]
                for indice, (nome, cor) in enumerate(OFICINAS_DEMO):
                    oficina, _ = Oficina.objects.get_or_create(nome=nome, defaults={'cor': cor})
                    atividade = AtividadeCronograma.objects.filter(
                        escola=escola, oficina=oficina,
                        dados_legados__demo=True,
                    ).first()
                    if atividade is None:
                        atividade = AtividadeCronograma.objects.create(
                            escola=escola, oficina=oficina,
                            turno=turnos[indice], dias_semana=[indice],
                            horario=f'{horarios[indice][0]:02d}:{horarios[indice][1]:02d}',
                            horario_fim=f'{horarios[indice][0] + 1:02d}:{horarios[indice][1]:02d}',
                            turmas=[AtividadeCronograma.Turma.values[indice % 3]],
                            dados_legados={'demo': True},
                        )
                    oficinas.append(atividade)
                alunos_existentes = alunos_demo(escola, user)
                quantidade_alvo = rng.randint(35, 45)
                quantidade_nova = max(0, quantidade_alvo - len(alunos_existentes))
                if quantidade_nova:
                    maior_id = escola.alunos.order_by('-pk').values_list('pk', flat=True).first() or 0
                    seed_alunos = seed + indice_escola if seed is not None else rng.randrange(1, 2**31)
                    call_command(
                        'popular_alunos', escola=escola.slug, quantidade=quantidade_nova,
                        seed=seed_alunos, stdout=StringIO(),
                    )
                    ids_novos = list(escola.alunos.filter(pk__gt=maior_id).values_list('pk', flat=True))
                    Aluno.objects.filter(pk__in=ids_novos).update(criado_por=user)
                    alunos_existentes.extend(Aluno.objects.filter(pk__in=ids_novos).order_by('pk'))

                if len(alunos_existentes) < 30:
                    raise CommandError(f'A carga de demonstração precisa de pelo menos 30 atendidos em {escola}.')
                for aluno in alunos_existentes:
                    aluno.turno = rng.choice(Aluno.Turno.values)
                    aluno.turma = rng.choice(Aluno.Turma.values)
                    aluno.save(update_fields=['turno', 'turma'])

                taxa_presenca = rng.uniform(0.60, 0.96)
                for dias_atras in range(1, 29):
                    data = hoje - timedelta(days=dias_atras)
                    if data.weekday() >= 5:
                        continue
                    for aluno in alunos_existentes:
                        # Não substitui uma presença que já tenha sido lançada pela gestão.
                        chamada, criada = ChamadaGeral.objects.get_or_create(
                            escola=escola, aluno=aluno, data=data,
                            defaults={'observacoes': 'Chamada fictícia para demonstração.'},
                        )
                        if criada or (chamada.lancado_por_id is None and chamada.atualizado_por_id is None
                                      and chamada.observacoes == 'Chamada fictícia para demonstração.'):
                            chamada.status_presenca = rng.choices(
                                ['P', 'F', 'J'], weights=[taxa_presenca * 0.85, 1 - taxa_presenca, taxa_presenca * 0.15],
                            )[0]
                            chamada.save(update_fields=['status_presenca', 'atualizado_em'])
                resumo.append((escola.nome, len(alunos_existentes), len(oficinas)))

        for nome, alunos, oficinas in resumo:
            self.stdout.write(f'{nome}: {alunos} atendidos, {oficinas} oficinas no cronograma e chamada geral.')
        for nome, username, senha in novas_contas:
            self.stdout.write(self.style.WARNING(
                f'Instrutor demo — {nome}: usuário {username} | senha temporária {senha}'
            ))
        if not novas_contas:
            self.stdout.write('As contas demo existentes foram mantidas; as senhas não foram alteradas.')
        self.stdout.write(self.style.SUCCESS(
            f'Dados de demonstração atualizados em {len(resumo)} unidade(s), com '
            f'{sum(row[1] for row in resumo)} atendidos e {sum(row[2] for row in resumo)} oficinas no cronograma.'
        ))
