from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('matriculas', '0002_atendidos_e_inativacao'),
        ('oficinas', '0009_remover_turno_noite'),
    ]

    operations = [
        migrations.AlterField(
            model_name='matricula',
            name='turno',
            field=models.CharField(
                choices=[('MANHA', 'Manhã'), ('TARDE', 'Tarde')],
                editable=False,
                max_length=10,
                verbose_name='turno',
            ),
        ),
    ]
