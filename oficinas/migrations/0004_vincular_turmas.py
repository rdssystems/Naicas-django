from django.db import migrations


def vincular(apps, schema_editor):
    banco = schema_editor.connection.alias
    Oficina = apps.get_model('oficinas', 'Oficina')
    Matricula = apps.get_model('matriculas', 'Matricula')
    for oficina in Oficina.objects.using(banco).all().iterator():
        turmas = sorted(set(Matricula.objects.using(banco).filter(
            oficina=oficina, status='CURSANDO', aluno__escola_id=oficina.escola_id,
            aluno__turno=oficina.turno, aluno__turma__in=['A', 'B', 'C'],
        ).values_list('aluno__turma', flat=True)))
        Oficina.objects.using(banco).filter(pk=oficina.pk).update(turmas=turmas)


class Migration(migrations.Migration):
    dependencies = [
        ('oficinas', '0003_oficina_turmas_alter_oficina_vagas'),
        ('matriculas', '0001_initial'), ('alunos', '0005_aluno_turma_aluno_turno'),
    ]
    operations = [migrations.RunPython(vincular, migrations.RunPython.noop)]
