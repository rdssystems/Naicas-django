from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models, transaction

from core.acesso import NivelAcesso

# Nome do Group do Django para cada nível (bundle de Permission padrão).
GRUPO_POR_NIVEL = {
    NivelAcesso.DIRETOR: 'Diretor',
    NivelAcesso.COORDENADOR: 'Coordenador',
    NivelAcesso.MONITOR: 'Monitor',
}


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile'
    )
    nivel_acesso = models.CharField(
        'nível de acesso', max_length=20, choices=NivelAcesso.choices
    )
    # Obrigatória só para Coordenador. Diretor e Monitor (global) ficam sem.
    escola = models.ForeignKey(
        'escolas.EscolaNaica',
        verbose_name='unidade',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='perfis',
    )

    class Meta:
        verbose_name = 'perfil'
        verbose_name_plural = 'perfis'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(nivel_acesso=NivelAcesso.COORDENADOR, escola__isnull=False)
                    | models.Q(
                        nivel_acesso__in=[NivelAcesso.DIRETOR, NivelAcesso.MONITOR],
                        escola__isnull=True,
                    )
                ),
                name='profile_escola_conforme_nivel',
                violation_error_message=(
                    'Coordenador precisa de unidade; Diretor e Monitor não podem ter unidade.'
                ),
            ),
        ]

    def __str__(self):
        return f'{self.user} ({self.get_nivel_acesso_display()})'

    def clean(self):
        if self.nivel_acesso == NivelAcesso.COORDENADOR and not self.escola_id:
            raise ValidationError({'escola': 'Coordenador precisa estar vinculado a uma unidade.'})
        if self.nivel_acesso in (NivelAcesso.DIRETOR, NivelAcesso.MONITOR) and self.escola_id:
            raise ValidationError({
                'escola': 'Diretor e Monitor são da rede inteira e não podem ter unidade.'
            })

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sincronizar_grupo()

    def sincronizar_grupo(self):
        """Mantém o usuário em exatamente um dos 3 Groups, o do seu nível."""
        grupos_de_papel = Group.objects.filter(name__in=GRUPO_POR_NIVEL.values())
        self.user.groups.remove(*grupos_de_papel)
        grupo, _ = Group.objects.get_or_create(name=GRUPO_POR_NIVEL[self.nivel_acesso])
        self.user.groups.add(grupo)
