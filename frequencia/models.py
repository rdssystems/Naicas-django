from django.conf import settings
from django.db import models

from matriculas.models import Matricula
from oficinas.models import AtividadeCronograma


class RegistroAula(models.Model):
    oficina = models.ForeignKey(AtividadeCronograma, on_delete=models.PROTECT, related_name='aulas')
    data_aula = models.DateField('data da aula')
    observacoes = models.TextField('observações da aula', blank=True)

    lancado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='lançado por', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    lancado_em = models.DateTimeField('lançado em', auto_now_add=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='alterado por', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    atualizado_em = models.DateTimeField('alterado em', auto_now=True)

    class Meta:
        verbose_name = 'registro de aula'
        verbose_name_plural = 'registros de aula'
        ordering = ['-data_aula']
        constraints = [
            models.UniqueConstraint(
                fields=['oficina', 'data_aula'], name='uma_aula_por_dia_por_oficina',
                violation_error_message='Já existe chamada desta oficina nesta data.',
            ),
        ]

    def __str__(self):
        return f'{self.oficina} — {self.data_aula:%d/%m/%Y}'


class Chamada(models.Model):
    class Presenca(models.TextChoices):
        PRESENTE = 'P', 'Presente'
        FALTA = 'F', 'Falta'
        JUSTIFICADA = 'J', 'Justificada'

    registro_aula = models.ForeignKey(RegistroAula, on_delete=models.CASCADE, related_name='chamadas')
    matricula = models.ForeignKey(Matricula, on_delete=models.PROTECT, related_name='chamadas')
    status_presenca = models.CharField('presença', max_length=1, choices=Presenca.choices)
    observacoes = models.CharField('observação', max_length=255, blank=True)

    class Meta:
        verbose_name = 'chamada'
        verbose_name_plural = 'chamadas'
        constraints = [
            models.UniqueConstraint(fields=['registro_aula', 'matricula'], name='uma_chamada_por_aluno_por_aula'),
        ]

    def __str__(self):
        return f'{self.matricula.aluno} — {self.get_status_presenca_display()}'


class ChamadaGeral(models.Model):
    """Presença diária na unidade, independente de oficinas e matrículas.

    Status vazio é reservado a históricos divergentes aguardando revisão.
    RegistroAula e Chamada permanecem apenas como arquivo do modelo anterior.
    """

    Presenca = Chamada.Presenca

    escola = models.ForeignKey('escolas.EscolaNaica', on_delete=models.PROTECT, related_name='chamadas_gerais')
    aluno = models.ForeignKey('alunos.Aluno', verbose_name='atendido', on_delete=models.PROTECT, related_name='chamadas_gerais')
    data = models.DateField('data da chamada')
    status_presenca = models.CharField('presença', max_length=1, choices=Presenca.choices, blank=True)
    observacoes = models.CharField('observação', max_length=255, blank=True)
    lancado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    lancado_em = models.DateTimeField('lançado em', auto_now_add=True)
    atualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    atualizado_em = models.DateTimeField('alterado em', auto_now=True)

    class Meta:
        verbose_name = 'chamada geral'
        verbose_name_plural = 'chamadas gerais'
        ordering = ['-data', 'aluno__nome']
        constraints = [
            models.UniqueConstraint(fields=['escola', 'aluno', 'data'], name='presenca_diaria_unica_na_unidade'),
            models.CheckConstraint(condition=models.Q(status_presenca__in=['', 'P', 'F', 'J']), name='presenca_geral_valida'),
        ]

    def __str__(self):
        return f'{self.aluno} — {self.data:%d/%m/%Y}'
