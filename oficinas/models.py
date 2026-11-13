from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from core.acesso import NivelAcesso


class Oficina(models.Model):
    """Catálogo único da rede: a própria oficina é a tag do cronograma."""

    nome = models.CharField('nome', max_length=100)
    cor = models.CharField(
        'cor', max_length=7, blank=True,
        validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Use uma cor no formato #RRGGBB.')],
    )
    arquivada = models.BooleanField('arquivada', default=False)

    class Meta:
        verbose_name = 'oficina'
        verbose_name_plural = 'oficinas'
        ordering = ['nome']
        constraints = [
            models.UniqueConstraint(Lower('nome'), name='oficina_nome_unico_na_rede'),
        ]

    def __str__(self):
        return self.nome


class AtividadeCronograma(models.Model):
    """Vínculo editável entre oficina, unidade, turmas e horário semanal."""

    class Turma(models.TextChoices):
        A = 'A', 'Turma A'
        B = 'B', 'Turma B'
        C = 'C', 'Turma C'

    class Turno(models.TextChoices):
        MANHA = 'MANHA', 'Manhã'
        TARDE = 'TARDE', 'Tarde'

    class DiaSemana(models.IntegerChoices):
        SEGUNDA = 0, 'Segunda'
        TERCA = 1, 'Terça'
        QUARTA = 2, 'Quarta'
        QUINTA = 3, 'Quinta'
        SEXTA = 4, 'Sexta'
        SABADO = 5, 'Sábado'
        DOMINGO = 6, 'Domingo'

    escola = models.ForeignKey(
        'escolas.EscolaNaica', verbose_name='unidade', on_delete=models.PROTECT,
        related_name='atividades_cronograma',
    )
    oficina = models.ForeignKey(
        Oficina, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='atividades', verbose_name='oficina',
    )
    turmas = ArrayField(
        models.CharField(max_length=1, choices=Turma.choices),
        verbose_name='turmas', default=list, blank=True,
    )
    turno = models.CharField('turno', max_length=10, choices=Turno.choices)
    dias_semana = ArrayField(
        models.PositiveSmallIntegerField(choices=DiaSemana.choices), verbose_name='dias da semana',
    )
    horario = models.TimeField('horário de início')
    horario_fim = models.TimeField('horário de término')
    instrutor_nome = models.CharField('instrutor', max_length=150, blank=True)
    ativo = models.BooleanField('ativo', default=True)
    # Somente para consulta dos registros antigos, inclusive após exclusão do catálogo.
    nome_legado = models.CharField('nome histórico', max_length=150, blank=True, editable=False)
    dados_legados = models.JSONField('dados históricos', default=dict, blank=True, editable=False)
    monitores = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, through='Designacao',
        related_name='oficinas_designadas', verbose_name='designações históricas',
    )

    class Meta:
        verbose_name = 'atividade do cronograma'
        verbose_name_plural = 'atividades do cronograma'
        ordering = ['escola__nome', 'horario', 'oficina__nome']

    @property
    def nome(self):
        return self.oficina.nome if self.oficina_id else self.nome_legado

    def __str__(self):
        return self.nome

    def clean(self):
        erros = {}
        if self.horario and self.horario_fim and self.horario_fim <= self.horario:
            erros['horario_fim'] = 'O horário de término precisa ser depois do de início.'
        if not self.dias_semana:
            erros['dias_semana'] = 'Escolha pelo menos um dia da semana.'
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        if not self.nome_legado and self.oficina_id:
            self.nome_legado = self.oficina.nome
        super().save(*args, **kwargs)

    @property
    def dias_semana_display(self):
        nomes = dict(self.DiaSemana.choices)
        return ', '.join(nomes[d][:3] for d in sorted(self.dias_semana or []))

    @property
    def turmas_display(self):
        return ', '.join(f'Turma {turma}' for turma in sorted(set(self.turmas))) or 'Turmas pendentes'


class Designacao(models.Model):
    """Arquivo das designações antigas; não atribui tarefas no fluxo atual."""

    oficina = models.ForeignKey(AtividadeCronograma, on_delete=models.CASCADE, related_name='designacoes')
    monitor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='designacoes',
        limit_choices_to={'profile__nivel_acesso': NivelAcesso.MONITOR},
    )
    dias_semana = ArrayField(
        models.PositiveSmallIntegerField(choices=AtividadeCronograma.DiaSemana.choices),
        verbose_name='dias históricos', default=list, blank=True,
    )

    class Meta:
        verbose_name = 'designação histórica'
        verbose_name_plural = 'designações históricas'
        constraints = [
            models.UniqueConstraint(fields=['oficina', 'monitor'], name='designacao_unica_por_oficina'),
        ]

    def __str__(self):
        return f'{self.monitor} em {self.oficina}'
