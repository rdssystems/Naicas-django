from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from core.acesso import NivelAcesso


class EscolaNaica(models.Model):
    nome = models.CharField('nome', max_length=150, unique=True)
    slug = models.SlugField('slug', max_length=160, unique=True, editable=False)
    endereco = models.CharField('endereço', max_length=255, blank=True)
    telefone = models.CharField('telefone', max_length=20, blank=True)
    email = models.EmailField('e-mail', blank=True)
    coordenador_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='coordenador responsável',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='escolas_coordenadas',
    )

    class Meta:
        verbose_name = 'Escola Naica'
        verbose_name_plural = 'Escolas Naica'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def clean(self):
        # O responsável precisa ser Coordenador desta mesma unidade.
        if self.coordenador_user_id:
            profile = getattr(self.coordenador_user, 'profile', None)
            if (
                profile is None
                or profile.nivel_acesso != NivelAcesso.COORDENADOR
                or profile.escola_id != self.pk
            ):
                raise ValidationError({
                    'coordenador_user': 'O responsável precisa ser um Coordenador desta unidade.'
                })

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._gerar_slug_unico()
        super().save(*args, **kwargs)

    def _gerar_slug_unico(self):
        base = slugify(self.nome)[:150] or 'escola'
        slug, n = base, 2
        while EscolaNaica.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug
