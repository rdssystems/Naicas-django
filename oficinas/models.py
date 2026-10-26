from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from core.acesso import NivelAcesso


class TipoOficina(models.Model):
    escola = models.ForeignKey(
        'escolas.EscolaNaica', verbose_name='unidade', on_delete=models.PROTECT,
        related_name='tipos_oficina',
    )
    nome = models.CharField('nome', max_length=100)
    cor = models.CharField(
        'cor', max_length=7, blank=True,
        validators=[RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Use uma cor no formato #RRGGBB.')],
        help_text='Opcional, só para identificar o tipo nas telas.',
    )

    class Meta:
        verbose_name = 'tipo de oficina'
        verbose_name_plural = 'tipos de oficina'
        ordering = ['escola__nome', 'nome']
        constraints = [
            models.UniqueConstraint(
                fields=['escola', 'nome'], name='tipo_oficina_unico_por_escola',
                violation_error_message='Já existe um tipo com esse nome nesta unidade.',
            ),
        ]

    def __str__(self):
        return self.nome


class Oficina(models.Model):
    class Turno(models.TextChoices):
        MANHA = 'MANHA', 'Manhã'
        TARDE = 'TARDE', 'Tarde'
        NOITE = 'NOITE', 'Noite'

    class Status(models.TextChoices):
        ABERTA = 'ABERTA', 'Aberta'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em andamento'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        ARQUIVADO = 'ARQUIVADO', 'Arquivado'

    class DiaSemana(models.IntegerChoices):
        # Mesma numeração do date.weekday() do Python (segunda = 0).
        SEGUNDA = 0, 'Segunda'
        TERCA = 1, 'Terça'
        QUARTA = 2, 'Quarta'
        QUINTA = 3, 'Quinta'
        SEXTA = 4, 'Sexta'
        SABADO = 5, 'Sábado'
        DOMINGO = 6, 'Domingo'

    # Sempre igual à escola do tipo (preenchida no save).
    escola = models.ForeignKey(
        'escolas.EscolaNaica', verbose_name='unidade', on_delete=models.PROTECT,
        related_name='oficinas', editable=False,
    )
    tipo_oficina = models.ForeignKey(
        TipoOficina, verbose_name='tipo', on_delete=models.PROTECT, related_name='oficinas',
    )
    nome = models.CharField('nome', max_length=150)
    carga_horaria = models.PositiveIntegerField('carga horária (horas)')
    vagas = models.PositiveIntegerField('vagas')
    data_inicio = models.DateField('data de início')
    data_fim = models.DateField('data de término')
    turno = models.CharField('turno', max_length=10, choices=Turno.choices)
    horario = models.TimeField('horário de início')
    horario_fim = models.TimeField('horário de término')
    dias_semana = ArrayField(
        models.PositiveSmallIntegerField(choices=DiaSemana.choices),
        verbose_name='dias da semana',
    )
    status = models.CharField(
        'status', max_length=20, choices=Status.choices, default=Status.ABERTA,
    )
    nome_monitor = models.CharField(
        'monitor (sem conta)', max_length=150, blank=True,
        help_text='Quem conduz a oficina sem ter conta no sistema.',
    )
    telefone_monitor = models.CharField('telefone do monitor', max_length=20, blank=True)
    # Escala: quem atende a oficina e em quais dias (ver Designacao).
    monitores = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name='monitores designados',
        blank=True,
        through='Designacao',
        related_name='oficinas_designadas',
    )

    class Meta:
        verbose_name = 'oficina'
        verbose_name_plural = 'oficinas'
        ordering = ['escola__nome', 'nome']

    def __str__(self):
        return self.nome

    def clean(self):
        erros = {}
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            erros['data_fim'] = 'A data de término não pode ser antes da data de início.'
        if self.horario and self.horario_fim and self.horario_fim <= self.horario:
            erros['horario_fim'] = 'O horário de término precisa ser depois do de início.'
        if not self.dias_semana:
            erros['dias_semana'] = 'Escolha pelo menos um dia da semana.'
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.escola_id = self.tipo_oficina.escola_id
        super().save(*args, **kwargs)
        self.ajustar_designacoes_aos_dias()

    def ajustar_designacoes_aos_dias(self):
        """
        Se a oficina perdeu dias, eles saem das designações. Designação que
        fica sem nenhum dia é removida (dias vazio significaria "todos").
        """
        for designacao in self.designacoes.exclude(dias_semana=[]):
            restantes = [d for d in designacao.dias_semana if d in self.dias_semana]
            if not restantes:
                designacao.delete()
            elif restantes != designacao.dias_semana:
                designacao.dias_semana = restantes
                designacao.save(update_fields=['dias_semana'])

    @property
    def dias_semana_display(self):
        nomes = dict(self.DiaSemana.choices)
        return ', '.join(nomes[d][:3] for d in sorted(self.dias_semana or []))


class Designacao(models.Model):
    """
    Escala: o monitor atende a oficina nos dias indicados.
    `dias_semana` vazio = todos os dias da oficina (acompanha mudanças nela).
    """

    oficina = models.ForeignKey(Oficina, on_delete=models.CASCADE, related_name='designacoes')
    monitor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='designacoes',
        limit_choices_to={'profile__nivel_acesso': NivelAcesso.MONITOR},
    )
    dias_semana = ArrayField(
        models.PositiveSmallIntegerField(choices=Oficina.DiaSemana.choices),
        verbose_name='dias que atende', default=list, blank=True,
        help_text='Vazio = todos os dias da oficina.',
    )

    class Meta:
        verbose_name = 'designação de monitor'
        verbose_name_plural = 'designações de monitores'
        constraints = [
            models.UniqueConstraint(fields=['oficina', 'monitor'], name='designacao_unica_por_oficina'),
        ]

    def __str__(self):
        return f'{self.monitor} em {self.oficina}'

    @property
    def dias_efetivos(self):
        return sorted(self.dias_semana) if self.dias_semana else sorted(self.oficina.dias_semana)

    @property
    def dias_display(self):
        nomes = dict(Oficina.DiaSemana.choices)
        return ', '.join(nomes[d][:3] for d in self.dias_efetivos)

    @property
    def todos_os_dias(self):
        return not self.dias_semana
