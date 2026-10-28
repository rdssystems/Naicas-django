"""Prepara dados fictícios para demonstrar o dashboard e os fluxos do Naicas.

Uso: python manage.py popular_demo [--seed 2026]
Cria 30 alunos, cinco oficinas, matrículas e quatro chamadas por oficina em
cada unidade. Só funciona com DEBUG=True e recusa duplicar a carga de demonstração.
"""

import random
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from escolas.models import EscolaNaica
from frequencia.models import Chamada, RegistroAula
from matriculas.models import Matricula
from oficinas.models import Oficina, TipoOficina


OFICINAS_DEMO = [
    ('Esporte e Movimento', '#2e7a4c'),
    ('Artes e Criatividade', '#c8471f'),
    ('Tecnologia', '#2b3a8c'),
    ('Música', '#f2b705'),
    ('Apoio Escolar', '#4a64c8'),
]


class Command(BaseCommand):
    help = 'Cria dados fictícios completos para demonstração do dashboard (somente desenvolvimento).'

    def add_arguments(self, parser):
        parser.add_argument('--seed', type=int, default=2026, help='Semente para manter as chamadas reproduzíveis.')

    def handle(self, *args, seed, **options):
        if not settings.DEBUG:
            raise CommandError('Comando de demonstração: só roda com DEBUG=True.')
        escolas = list(EscolaNaica.objects.order_by('pk'))
        if not escolas:
            raise CommandError('Nenhuma unidade cadastrada. Rode as migrações primeiro.')
        if Oficina.objects.filter(nome__startswith='[DEMO]').exists():
            raise CommandError('A carga de demonstração já existe. Ela não foi duplicada.')

        rng = random.Random(seed)
        hoje = timezone.localdate()
        criados = []
        with transaction.atomic():
            for indice_escola, escola in enumerate(escolas):
                primeiro_id = (escola.alunos.order_by('-pk').values_list('pk', flat=True).first() or 0)
                call_command(
                    'popular_alunos', escola=escola.slug, quantidade=30,
                    seed=seed + indice_escola, stdout=StringIO(),
                )
                alunos = list(escola.alunos.filter(pk__gt=primeiro_id).order_by('pk'))
                if len(alunos) != 30:
                    raise CommandError(f'Não foi possível criar 30 alunos fictícios em {escola}.')

                oficinas = []
                for indice, (nome_tipo, cor) in enumerate(OFICINAS_DEMO):
                    tipo, _ = TipoOficina.objects.get_or_create(
                        escola=escola, nome=nome_tipo, defaults={'cor': cor},
                    )
                    oficina = Oficina.objects.create(
                        tipo_oficina=tipo,
                        nome=f'[DEMO] {nome_tipo} · {escola.nome}',
                        carga_horaria=40,
                        vagas=20,
                        data_inicio=hoje - timedelta(days=35),
                        data_fim=hoje + timedelta(days=35),
                        turno=Oficina.Turno.TARDE,
                        horario=f'{13 + indice:02d}:00',
                        horario_fim=f'{14 + indice:02d}:00',
                        dias_semana=[indice],
                        status=Oficina.Status.EM_ANDAMENTO,
                    )
                    oficinas.append(oficina)

                inscricoes = []
                for indice_aluno, aluno in enumerate(alunos):
                    # Duas oficinas em dias diferentes para não criar conflito de horário.
                    indices = (indice_aluno % 5, (indice_aluno + 2) % 5)
                    for indice_oficina in indices:
                        oficina = oficinas[indice_oficina]
                        inscricoes.append(Matricula(
                            aluno=aluno,
                            oficina=oficina,
                            escola=escola,
                            turno=oficina.turno,
                            data_inscricao=hoje - timedelta(days=30),
                            status=Matricula.Status.CURSANDO,
                        ))
                inscricoes = Matricula.objects.bulk_create(inscricoes)

                for indice_oficina, oficina in enumerate(oficinas):
                    matriculas = [m for m in inscricoes if m.oficina_id == oficina.pk]
                    datas_aula = [
                        hoje - timedelta(days=(hoje.weekday() - indice_oficina) % 7 + 7 * semana)
                        for semana in (1, 2, 3, 4)
                    ]
                    for data_aula in datas_aula:
                        registro = RegistroAula.objects.create(
                            oficina=oficina,
                            data_aula=data_aula,
                            observacoes='Chamada fictícia para demonstração.',
                        )
                        chamadas = []
                        for matricula in matriculas:
                            presenca = rng.choices(
                                [Chamada.Presenca.PRESENTE, Chamada.Presenca.FALTA, Chamada.Presenca.JUSTIFICADA],
                                weights=[80, 13, 7],
                            )[0]
                            chamadas.append(Chamada(
                                registro_aula=registro,
                                matricula=matricula,
                                status_presenca=presenca,
                            ))
                        Chamada.objects.bulk_create(chamadas)
                criados.append((escola.nome, len(alunos), len(oficinas), len(inscricoes)))

        for nome, alunos, oficinas, matriculas in criados:
            self.stdout.write(f'{nome}: {alunos} alunos, {oficinas} oficinas, {matriculas} matrículas.')
        self.stdout.write(self.style.SUCCESS(
            f'Demonstração criada em {len(criados)} unidade(s), com {sum(row[1] for row in criados)} alunos.'
        ))
