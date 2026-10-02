"""Tipos de documento sugeridos no spec. O Diretor pode mudar depois pelo painel."""

from django.db import migrations

# (nome, obrigatório)
TIPOS = [
    ('Certidão de nascimento ou RG do aluno', True),
    ('CPF do aluno', True),
    ('Documento com foto do responsável', True),
    ('Comprovante de endereço', True),
    ('Declaração de matrícula escolar', True),
    ('Termo de autorização de uso de imagem', True),
    ('Cartão SUS', False),
    ('Comprovante de NIS/CadÚnico', False),
    ('Laudo médico', False),
    ('Foto 3x4', False),
]


def criar_tipos(apps, schema_editor):
    TipoDocumento = apps.get_model('anexos', 'TipoDocumento')
    for ordem, (nome, obrigatorio) in enumerate(TIPOS, start=1):
        TipoDocumento.objects.get_or_create(nome=nome, defaults={'obrigatorio': obrigatorio, 'ordem': ordem * 10})


def remover_tipos(apps, schema_editor):
    TipoDocumento = apps.get_model('anexos', 'TipoDocumento')
    TipoDocumento.objects.filter(nome__in=[nome for nome, _ in TIPOS], anexos__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('anexos', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(criar_tipos, remover_tipos),
    ]
