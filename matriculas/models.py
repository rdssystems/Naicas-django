from django.conf import settings
from django.db import models
from django.db.models import Q

from oficinas.models import Oficina


class Matricula(models.Model):
    class Status(models.TextChoices):
        CURSANDO = 'CURSANDO', 'Cursando'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        DESISTENTE = 'DESISTENTE', 'Desistente'

    # PROTECT: matrícula é histórico (frequência vai apontar para ela).
    aluno = models.ForeignKey('alunos.Aluno', on_delete=models.PROTECT, related_name='matriculas')
    oficina = models.ForeignKey(Oficina, on_delete=models.PROTECT, related_name='matriculas')
    # Copiados da oficina no momento da matrícula (histórico).
    escola = models.ForeignKey(
        'escolas.EscolaNaica', verbose_name='unidade de atendimento', on_delete=models.PROTECT,
        related_name='matriculas', editable=False,
    )
    turno = models.CharField('turno', max_length=10, choices=Oficina.Turno.choices, editable=False)

    data_inscricao = models.DateField('data de inscrição', auto_now_add=True)
    status = models.CharField('situação', max_length=20, choices=Status.choices, default=Status.CURSANDO)
    data_conclusao = models.DateField('data de conclusão', null=True, blank=True)
    data_desistencia = models.DateField('data de desistência', null=True, blank=True)
    matriculado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='matriculado por', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    class Meta:
        verbose_name = 'matrícula'
        verbose_name_plural = 'matrículas'
        ordering = ['-data_inscricao', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['aluno', 'oficina'], condition=Q(status='CURSANDO'),
                name='matricula_cursando_unica_por_oficina',
                violation_error_message='O aluno já está cursando esta oficina.',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status='CURSANDO', data_conclusao__isnull=True, data_desistencia__isnull=True)
                    | Q(status='CONCLUIDO', data_conclusao__isnull=False)
                    | Q(status='DESISTENTE', data_desistencia__isnull=False)
                ),
                name='matricula_data_conforme_status',
            ),
        ]

    def __str__(self):
        return f'{self.aluno} em {self.oficina}'

    def save(self, *args, **kwargs):
        if not self.pk:
            self.escola_id = self.oficina.escola_id
            self.turno = self.oficina.turno
        super().save(*args, **kwargs)
