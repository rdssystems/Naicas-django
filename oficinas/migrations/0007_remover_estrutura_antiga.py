from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [('oficinas', '0006_alter_designacao_options_and_more')]
    operations = [
        migrations.RemoveField('oficina', 'escola'),
        *[migrations.RemoveField('atividadecronograma', campo) for campo in (
            'nome', 'carga_horaria', 'vagas', 'data_inicio', 'data_fim',
            'status', 'nome_monitor', 'telefone_monitor',
        )],
        migrations.AlterModelOptions('oficina', {
            'ordering': ['nome'], 'verbose_name': 'oficina', 'verbose_name_plural': 'oficinas',
        }),
        migrations.AlterModelOptions('atividadecronograma', {
            'ordering': ['escola__nome', 'horario', 'oficina__nome'],
            'verbose_name': 'atividade do cronograma', 'verbose_name_plural': 'atividades do cronograma',
        }),
        migrations.AddConstraint('oficina', models.UniqueConstraint(Lower('nome'), name='oficina_nome_unico_na_rede')),
    ]
