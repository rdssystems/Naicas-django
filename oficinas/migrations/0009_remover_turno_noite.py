from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('oficinas', '0008_instrutor_do_cronograma'),
    ]

    operations = [
        migrations.AlterField(
            model_name='atividadecronograma',
            name='turno',
            field=models.CharField(
                choices=[('MANHA', 'Manhã'), ('TARDE', 'Tarde')],
                max_length=10,
                verbose_name='turno',
            ),
        ),
    ]
