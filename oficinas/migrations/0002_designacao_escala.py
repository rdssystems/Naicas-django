"""
Escala: o vínculo Oficina <-> Monitor ganha os dias da semana.

O Django não converte um ManyToMany simples em um com `through`, então:
1. cria Designacao;
2. copia os vínculos atuais (dias vazio = todos os dias da oficina, igual a antes);
3. remove o campo antigo e recria `monitores` usando Designacao.
"""

import django.contrib.postgres.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copiar_vinculos(apps, schema_editor):
    Oficina = apps.get_model('oficinas', 'Oficina')
    Designacao = apps.get_model('oficinas', 'Designacao')
    for vinculo in Oficina.monitores.through.objects.all():
        Designacao.objects.get_or_create(oficina_id=vinculo.oficina_id, monitor_id=vinculo.user_id)


class Migration(migrations.Migration):

    dependencies = [
        ('oficinas', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Designacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dias_semana', django.contrib.postgres.fields.ArrayField(
                    base_field=models.PositiveSmallIntegerField(choices=[
                        (0, 'Segunda'), (1, 'Terça'), (2, 'Quarta'), (3, 'Quinta'),
                        (4, 'Sexta'), (5, 'Sábado'), (6, 'Domingo'),
                    ]),
                    blank=True, default=list, help_text='Vazio = todos os dias da oficina.', size=None,
                    verbose_name='dias que atende',
                )),
                ('monitor', models.ForeignKey(
                    limit_choices_to={'profile__nivel_acesso': 'MONITOR'},
                    on_delete=django.db.models.deletion.CASCADE, related_name='designacoes',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('oficina', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='designacoes', to='oficinas.oficina',
                )),
            ],
            options={
                'verbose_name': 'designação de monitor',
                'verbose_name_plural': 'designações de monitores',
                'constraints': [
                    models.UniqueConstraint(fields=('oficina', 'monitor'), name='designacao_unica_por_oficina'),
                ],
            },
        ),
        migrations.RunPython(copiar_vinculos, migrations.RunPython.noop),
        migrations.RemoveField(model_name='oficina', name='monitores'),
        migrations.AddField(
            model_name='oficina',
            name='monitores',
            field=models.ManyToManyField(
                blank=True, related_name='oficinas_designadas', through='oficinas.Designacao',
                to=settings.AUTH_USER_MODEL, verbose_name='monitores designados',
            ),
        ),
    ]
