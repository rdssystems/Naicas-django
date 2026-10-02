"""
Cria os 3 Groups de papel e dá Profile de Diretor aos superusers que já
existem (ex.: o criado com createsuperuser antes desta etapa).

As Permissions de cada Group são adicionadas pelas migrações dos apps de
domínio, conforme eles forem criados.
"""

from django.conf import settings
from django.db import migrations

GRUPOS = ['Diretor', 'Coordenador', 'Monitor']


def criar_grupos_e_perfis(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Profile = apps.get_model('usuarios', 'Profile')

    for nome in GRUPOS:
        Group.objects.get_or_create(name=nome)

    grupo_diretor = Group.objects.get(name='Diretor')
    for user in User.objects.filter(is_superuser=True, profile__isnull=True):
        Profile.objects.create(user=user, nivel_acesso='DIRETOR', escola=None)
        user.groups.add(grupo_diretor)


def remover_grupos(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name__in=GRUPOS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(criar_grupos_e_perfis, remover_grupos),
    ]
