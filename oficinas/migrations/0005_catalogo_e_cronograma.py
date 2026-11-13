import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower


def unificar(apps, schema_editor):
    banco = schema_editor.connection.alias
    Oficina = apps.get_model('oficinas', 'Oficina')
    Atividade = apps.get_model('oficinas', 'AtividadeCronograma')
    for item in Atividade.objects.using(banco).select_related('oficina').all().iterator():
        dados = {
            campo: str(getattr(item, campo)) if getattr(item, campo) is not None else None
            for campo in ('data_inicio', 'data_fim', 'carga_horaria', 'vagas', 'status',
                          'nome_monitor', 'telefone_monitor')
        }
        dados['tag_anterior'] = {
            'id': item.oficina_id, 'nome': item.oficina.nome,
            'cor': item.oficina.cor, 'escola_id': item.escola_id,
        }
        if item.nome.startswith('[DEMO]'):
            dados['demo'] = True
        Atividade.objects.using(banco).filter(pk=item.pk).update(
            nome_legado=item.nome, dados_legados=dados, ativo=item.status in ('ABERTA', 'EM_ANDAMENTO'),
        )
    catalogo = {}
    for oficina in Oficina.objects.using(banco).order_by('pk').iterator():
        nome = oficina.nome.strip()
        chave = nome.casefold()
        if chave in catalogo:
            destino = catalogo[chave]
            Atividade.objects.using(banco).filter(oficina_id=oficina.pk).update(oficina_id=destino)
            Oficina.objects.using(banco).filter(pk=oficina.pk).delete()
        else:
            catalogo[chave] = oficina.pk
            Oficina.objects.using(banco).filter(pk=oficina.pk).update(nome=nome)
    for oficina_id in catalogo.values():
        atividades = Atividade.objects.using(banco).filter(oficina_id=oficina_id)
        if atividades.exists() and not atividades.filter(ativo=True).exists():
            Oficina.objects.using(banco).filter(pk=oficina_id).update(arquivada=True)


class Migration(migrations.Migration):
    dependencies = [
        ('oficinas', '0004_vincular_turmas'),
        ('frequencia', '0003_consolidar_historico'),
        ('matriculas', '0001_initial'),
    ]
    operations = [
        migrations.RenameModel('Oficina', 'AtividadeCronograma'),
        migrations.RenameModel('TipoOficina', 'Oficina'),
        migrations.RemoveConstraint('oficina', 'tipo_oficina_unico_por_escola'),
        migrations.RenameField('atividadecronograma', 'tipo_oficina', 'oficina'),
        migrations.AddField('oficina', 'arquivada', models.BooleanField(default=False, verbose_name='arquivada')),
        migrations.AddField('atividadecronograma', 'ativo', models.BooleanField(default=True, verbose_name='ativo')),
        migrations.AddField('atividadecronograma', 'nome_legado', models.CharField(blank=True, editable=False, max_length=150, verbose_name='nome histórico')),
        migrations.AddField('atividadecronograma', 'dados_legados', models.JSONField(blank=True, default=dict, editable=False, verbose_name='dados históricos')),
        migrations.AlterField('atividadecronograma', 'oficina', models.ForeignKey(
            to='oficinas.oficina', on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True,
            related_name='atividades', verbose_name='oficina')),
    ]
