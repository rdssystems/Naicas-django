"""
As 10 unidades Naica de Uberlândia (dados enviados pela Secretaria em 2026-10-07).

update_or_create pelo nome: em bancos onde a unidade já existe (ex.: "Naica
Canaã" do ambiente de dev), só atualiza endereço/telefone/e-mail, preservando
oficinas, alunos e matrículas ligados a ela. Em banco novo (produção), cria.
"""

from django.db import migrations
from django.utils.text import slugify

# (bairro, endereço, telefone, e-mail)
UNIDADES = [
    ('Canaã', 'Rua Calixto Felipe Milken, 485', '3237-7322', 'naicacanaa@uberlandia.mg.gov.br'),
    ('Jardim Célia', 'Rua dos Sininhos, 35', '3217-7567', 'naicajardimcelia@uberlandia.mg.gov.br'),
    ('Lagoinha', 'Rua Coronel Antônio Alves Pereira, 2660', '3226-7719', 'naicalagoinha@uberlandia.mg.gov.br'),
    ('Luizote de Freitas', 'Rua Genarino Cazabona, 954', '3238-8604', 'naicaluizote@uberlandia.mg.gov.br'),
    ('Mansour', 'Rua Rio Uaupes, 36', '3234-8733', 'naicamansour@uberlandia.mg.gov.br'),
    ('Marta Helena', 'Sebastião Vieira de Souza, 150', '3211-2456', 'naicamartahelena@uberlandia.mg.gov.br'),
    ('Morumbi', 'Felipe Calixto Milken, 137', '3227-7674', 'naicamorumbi@uberlandia.mg.gov.br'),
    ('Pequis', 'Rua Wilson Rodrigues da Silva, 880', '3215-4961', 'naicapequis@uberlandia.mg.gov.br'),
    ('Tibery', 'Avenida Europa, 175', '3213-5998', 'naicatibery@uberlandia.mg.gov.br'),
    ('Tocantins', 'Rua Renato José Luiz, 90', '3210-9758', 'naicatocantins@uberlandia.mg.gov.br'),
]


def slug_unico(EscolaNaica, nome, pk=None):
    # Migração não chama EscolaNaica.save(), que é quem gera o slug.
    base = slugify(nome)[:150] or 'escola'
    slug, n = base, 2
    while EscolaNaica.objects.filter(slug=slug).exclude(pk=pk).exists():
        slug = f'{base}-{n}'
        n += 1
    return slug


def criar_unidades(apps, schema_editor):
    EscolaNaica = apps.get_model('escolas', 'EscolaNaica')
    for bairro, rua, telefone, email in UNIDADES:
        escola, _ = EscolaNaica.objects.update_or_create(
            nome=f'Naica {bairro}',
            defaults={
                'endereco': f'{rua} – {bairro}, Uberlândia/MG',
                'telefone': f'(34) {telefone}',
                'email': email,
            },
        )
        if not escola.slug:
            escola.slug = slug_unico(EscolaNaica, escola.nome, escola.pk)
            escola.save(update_fields=['slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('escolas', '0001_initial'),
    ]

    operations = [
        # Sem reverso: desfazer apagaria unidades que podem já ter dados ligados.
        migrations.RunPython(criar_unidades, migrations.RunPython.noop),
    ]
