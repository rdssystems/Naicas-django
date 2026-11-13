from itertools import groupby

from django.db import migrations


def consolidar(apps, schema_editor):
    banco = schema_editor.connection.alias
    Legada = apps.get_model('frequencia', 'Chamada')
    Geral = apps.get_model('frequencia', 'ChamadaGeral')
    linhas = Legada.objects.using(banco).select_related('registro_aula__oficina', 'matricula').order_by(
        'registro_aula__oficina__escola_id', 'registro_aula__data_aula', 'matricula__aluno_id', 'pk',
    )
    chave = lambda c: (c.registro_aula.oficina.escola_id, c.registro_aula.data_aula, c.matricula.aluno_id)
    for (escola_id, data, aluno_id), grupo in groupby(linhas.iterator(chunk_size=500), chave):
        registros = list(grupo)
        status = {chamada.status_presenca for chamada in registros}
        presenca = status.pop() if len(status) == 1 else ''
        observacoes = ' | '.join(dict.fromkeys(c.observacoes for c in registros if c.observacoes))
        if not presenca:
            observacoes = 'Histórico divergente entre oficinas; revisar presença. ' + observacoes
        primeiro = min(registros, key=lambda c: c.registro_aula.lancado_em).registro_aula
        ultimo = max(registros, key=lambda c: c.registro_aula.atualizado_em).registro_aula
        geral, criada = Geral.objects.using(banco).get_or_create(
            escola_id=escola_id, data=data, aluno_id=aluno_id,
            defaults={'status_presenca': presenca, 'observacoes': observacoes[:255],
                      'lancado_por_id': primeiro.lancado_por_id, 'atualizado_por_id': ultimo.atualizado_por_id},
        )
        if criada:
            Geral.objects.using(banco).filter(pk=geral.pk).update(
                lancado_em=primeiro.lancado_em, atualizado_em=ultimo.atualizado_em,
            )


class Migration(migrations.Migration):
    dependencies = [('frequencia', '0002_chamadageral')]
    # Reverter o esquema não altera o arquivo original por oficina.
    operations = [migrations.RunPython(consolidar, migrations.RunPython.noop)]
