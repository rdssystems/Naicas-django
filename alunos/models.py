from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from core import acesso
from core.validators import validar_cep, validar_cpf, validar_nis

from . import etapas


class UF(models.TextChoices):
    AC = 'AC', 'AC'
    AL = 'AL', 'AL'
    AP = 'AP', 'AP'
    AM = 'AM', 'AM'
    BA = 'BA', 'BA'
    CE = 'CE', 'CE'
    DF = 'DF', 'DF'
    ES = 'ES', 'ES'
    GO = 'GO', 'GO'
    MA = 'MA', 'MA'
    MT = 'MT', 'MT'
    MS = 'MS', 'MS'
    MG = 'MG', 'MG'
    PA = 'PA', 'PA'
    PB = 'PB', 'PB'
    PR = 'PR', 'PR'
    PE = 'PE', 'PE'
    PI = 'PI', 'PI'
    RJ = 'RJ', 'RJ'
    RN = 'RN', 'RN'
    RS = 'RS', 'RS'
    RO = 'RO', 'RO'
    RR = 'RR', 'RR'
    SC = 'SC', 'SC'
    SP = 'SP', 'SP'
    SE = 'SE', 'SE'
    TO = 'TO', 'TO'


class Parentesco(models.TextChoices):
    """Lista única usada em responsável, composição familiar e contatos de emergência."""

    MAE = 'MAE', 'Mãe'
    PAI = 'PAI', 'Pai'
    PADRASTO = 'PADRASTO', 'Madrasta/Padrasto'
    AVO = 'AVO', 'Avó/Avô'
    TIO = 'TIO', 'Tia/Tio'
    IRMAO = 'IRMAO', 'Irmã/Irmão'
    PRIMO = 'PRIMO', 'Prima/Primo'
    PADRINHO = 'PADRINHO', 'Madrinha/Padrinho'
    TUTOR = 'TUTOR', 'Tutor(a) legal'
    VIZINHO = 'VIZINHO', 'Vizinha/Vizinho'
    AMIGO = 'AMIGO', 'Amiga/Amigo da família'
    OUTRO = 'OUTRO', 'Outro'


class AlunoQuerySet(models.QuerySet):
    def visiveis_para(self, user):
        """
        Diretor: todos. Coordenador: cadastrados na unidade dele (e, a partir da
        Etapa 5, os matriculados em oficinas dela). Monitor: nenhum — ele não
        acessa o cadastro, só a lista de matriculados das oficinas dele.
        """
        if acesso.is_diretor(user):
            return self
        if acesso.is_coordenador(user):
            return self.filter(Q(escola=acesso.escola_do_usuario(user)))
        return self.none()


class Aluno(models.Model):
    class Sexo(models.TextChoices):
        FEMININO = 'F', 'Feminino'
        MASCULINO = 'M', 'Masculino'
        OUTRO = 'O', 'Outro'

    class AnoEscolar(models.TextChoices):
        INFANTIL = 'INFANTIL', 'Educação Infantil'
        EF1 = 'EF1', '1º ano (Fundamental)'
        EF2 = 'EF2', '2º ano (Fundamental)'
        EF3 = 'EF3', '3º ano (Fundamental)'
        EF4 = 'EF4', '4º ano (Fundamental)'
        EF5 = 'EF5', '5º ano (Fundamental)'
        EF6 = 'EF6', '6º ano (Fundamental)'
        EF7 = 'EF7', '7º ano (Fundamental)'
        EF8 = 'EF8', '8º ano (Fundamental)'
        EF9 = 'EF9', '9º ano (Fundamental)'
        EM1 = 'EM1', '1ª série (Médio)'
        EM2 = 'EM2', '2ª série (Médio)'
        EM3 = 'EM3', '3ª série (Médio)'
        EJA = 'EJA', 'EJA'
        NAO_ESTUDA = 'NAO_ESTUDA', 'Não está estudando'

    # Unidade de cadastro: define qual Coordenador enxerga o aluno.
    escola = models.ForeignKey(
        'escolas.EscolaNaica', verbose_name='unidade de cadastro',
        on_delete=models.PROTECT, related_name='alunos',
    )
    # Identificação
    cpf = models.CharField('CPF', max_length=11, unique=True, validators=[validar_cpf])
    nome = models.CharField('nome completo', max_length=150)
    nome_mae = models.CharField('nome da mãe', max_length=150)
    data_nascimento = models.DateField('data de nascimento')
    sexo = models.CharField('sexo', max_length=1, choices=Sexo.choices)
    naturalidade = models.CharField('naturalidade', max_length=100, help_text='Cidade/UF de nascimento.')
    nis = models.CharField('NIS', max_length=11, blank=True, validators=[validar_nis])
    # Escolaridade
    nome_escola = models.CharField('nome da escola', max_length=150)
    ano_escolar = models.CharField('ano escolar', max_length=20, choices=AnoEscolar.choices)

    criado_em = models.DateTimeField('criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('atualizado em', auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='criado por', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    objects = AlunoQuerySet.as_manager()

    class Meta:
        verbose_name = 'aluno'
        verbose_name_plural = 'alunos'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    # --- Progresso do cadastro: ver alunos/etapas.py (registro de etapas) ---

    def etapas(self):
        """Lista (número, nome, url_name, concluída?, disponível?) para a navegação."""
        return etapas.etapas_do_aluno(self)

    def vinculos_fora_da_familia(self):
        """
        Responsáveis do aluno que ainda não estão na composição familiar.
        Compara pelo vínculo (linha pré-preenchida) e também pelo nome, para
        não duplicar quem foi digitado à mão.
        """
        membros = list(self.membros_familia.all())
        ja_ligados = {m.responsavel_id for m in membros if m.responsavel_id}
        nomes = {m.nome.strip().casefold() for m in membros}
        return [
            v for v in self.responsaveis_vinculos.select_related('responsavel')
            if v.responsavel_id not in ja_ligados and v.responsavel.nome.strip().casefold() not in nomes
        ]

    @property
    def renda_familiar(self):
        """Soma simples da renda dos membros (sem score/priorização)."""
        return sum((m.renda_mensal for m in self.membros_familia.all()), start=0)

    @property
    def cadastro_completo(self):
        return etapas.cadastro_completo(self)


class Endereco(models.Model):
    aluno = models.OneToOneField(Aluno, on_delete=models.CASCADE, related_name='endereco')
    cep = models.CharField('CEP', max_length=8, validators=[validar_cep])
    logradouro = models.CharField('logradouro', max_length=200)
    numero = models.CharField('número', max_length=20, blank=True, help_text='Deixe vazio se for S/N.')
    bairro = models.CharField('bairro', max_length=100)
    complemento = models.CharField('complemento', max_length=100, blank=True)
    cidade = models.CharField('cidade', max_length=100)
    estado = models.CharField('estado', max_length=2, choices=UF.choices)

    class Meta:
        verbose_name = 'endereço'
        verbose_name_plural = 'endereços'

    def __str__(self):
        numero = self.numero or 'S/N'
        return f'{self.logradouro}, {numero} — {self.bairro}, {self.cidade}/{self.estado}'


class Responsavel(models.Model):
    """Entidade da rede, reaproveitada pelo CPF entre alunos (irmãos) e unidades."""

    cpf = models.CharField('CPF', max_length=11, unique=True, validators=[validar_cpf])
    nome = models.CharField('nome completo', max_length=150)
    data_nascimento = models.DateField('data de nascimento')
    # Contato
    celular = models.CharField('celular', max_length=20)
    email = models.EmailField('e-mail', blank=True)
    # Documento
    documento_numero = models.CharField('número do documento', max_length=30)
    documento_data_expedicao = models.DateField('data de expedição')
    documento_orgao_expedidor = models.CharField('órgão expedidor', max_length=30)
    documento_uf = models.CharField('UF do documento', max_length=2, choices=UF.choices)
    # Trabalho e renda
    trabalha = models.BooleanField('trabalha?')
    carteira_assinada = models.BooleanField('carteira assinada?', null=True, blank=True)
    ctps_numero = models.CharField('nº da CTPS', max_length=20, blank=True)
    ctps_serie = models.CharField('série da CTPS', max_length=20, blank=True)
    contribui_previdencia = models.BooleanField('contribui com a Previdência?', null=True, blank=True)
    recebe_beneficio = models.BooleanField('recebe algum benefício?')
    qual_beneficio = models.CharField('qual benefício', max_length=150, blank=True)

    atualizado_em = models.DateTimeField('atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'responsável'
        verbose_name_plural = 'responsáveis'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def clean(self):
        # Campos condicionais: só valem quando a pergunta anterior é "Sim".
        erros = {}
        if self.trabalha:
            if self.carteira_assinada is None:
                erros['carteira_assinada'] = 'Informe se a carteira é assinada.'
            elif self.carteira_assinada and not (self.ctps_numero and self.ctps_serie):
                erros['ctps_numero'] = 'Informe o número e a série da CTPS.'
        if self.recebe_beneficio and not self.qual_beneficio:
            erros['qual_beneficio'] = 'Informe qual benefício.'
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        # Limpa respostas que deixaram de valer (ex.: passou a "não trabalha").
        if not self.trabalha:
            self.carteira_assinada = None
        if not self.carteira_assinada:
            self.ctps_numero = self.ctps_serie = ''
        if not self.recebe_beneficio:
            self.qual_beneficio = ''
        super().save(*args, **kwargs)


class AlunoResponsavel(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='responsaveis_vinculos')
    responsavel = models.ForeignKey(Responsavel, on_delete=models.PROTECT, related_name='alunos_vinculos')
    grau_parentesco = models.CharField('grau de parentesco', max_length=20, choices=Parentesco.choices)

    class Meta:
        verbose_name = 'vínculo aluno-responsável'
        verbose_name_plural = 'vínculos aluno-responsável'
        constraints = [
            models.UniqueConstraint(fields=['aluno', 'responsavel'], name='aluno_responsavel_unico'),
        ]

    def __str__(self):
        return f'{self.responsavel} ({self.get_grau_parentesco_display()}) de {self.aluno}'


class MembroFamiliar(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='membros_familia')
    # Preenchido quando a linha veio de um responsável do aluno (pré-preenchimento
    # da etapa 3): é como o sistema sabe quem já está na composição familiar.
    responsavel = models.ForeignKey(
        Responsavel, verbose_name='responsável de origem', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    nome = models.CharField('nome', max_length=150)
    parentesco = models.CharField('parentesco', max_length=20, choices=Parentesco.choices)
    data_nascimento = models.DateField('data de nascimento', null=True, blank=True)
    ocupacao = models.CharField('ocupação', max_length=100, blank=True)
    renda_mensal = models.DecimalField(
        'renda mensal (R$)', max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        verbose_name = 'membro familiar'
        verbose_name_plural = 'membros familiares'
        ordering = ['pk']

    def __str__(self):
        return f'{self.nome} ({self.get_parentesco_display()})'


class ContatoEmergencia(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='contatos_emergencia')
    nome = models.CharField('nome', max_length=150)
    parentesco = models.CharField('parentesco', max_length=20, choices=Parentesco.choices)
    celular = models.CharField('celular', max_length=20)

    class Meta:
        verbose_name = 'contato de emergência'
        verbose_name_plural = 'contatos de emergência'
        ordering = ['pk']

    def __str__(self):
        return f'{self.nome} ({self.get_parentesco_display()})'


class FichaSaude(models.Model):
    """
    Dado sensível (LGPD). Quem pode ver é decidido SÓ por
    core.acesso.pode_ver_saude_completa / pode_ver_saude_emergencia.
    """

    class Assistencia(models.TextChoices):
        SUS = 'SUS', 'SUS'
        PLANO = 'PLANO', 'Plano de saúde'
        AMBOS = 'AMBOS', 'SUS e plano de saúde'

    aluno = models.OneToOneField(Aluno, on_delete=models.CASCADE, related_name='ficha_saude')
    # Assistência médica
    tipo_assistencia = models.CharField('assistência médica', max_length=10, choices=Assistencia.choices)
    plano_saude = models.CharField('qual(is) plano(s)', max_length=150, blank=True)
    # Condições
    possui_problema_saude = models.BooleanField('possui algum problema de saúde?')
    problema_saude = models.TextField('especifique o problema de saúde', blank=True)
    # Medicação controlada (Sim/Não + detalhes: no formulário da Prodaub era um texto só)
    usa_medicacao_controlada = models.BooleanField('usa medicação controlada?')
    medicacao = models.CharField('qual medicação', max_length=200, blank=True)
    medicacao_ha_quanto_tempo = models.CharField('há quanto tempo', max_length=100, blank=True)
    medicacao_reacoes = models.TextField('reações provocadas', blank=True)
    # Alergias (vazio = nenhuma conhecida)
    alergias = models.TextField('alergias', blank=True, help_text='Deixe em branco se não houver alergia conhecida.')

    atualizado_em = models.DateTimeField('atualizado em', auto_now=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='atualizado por', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )

    class Meta:
        verbose_name = 'ficha de saúde'
        verbose_name_plural = 'fichas de saúde'

    def __str__(self):
        return f'Ficha de saúde de {self.aluno}'

    def clean(self):
        erros = {}
        if self.tipo_assistencia in (self.Assistencia.PLANO, self.Assistencia.AMBOS) and not self.plano_saude:
            erros['plano_saude'] = 'Informe qual plano de saúde.'
        if self.possui_problema_saude and not self.problema_saude:
            erros['problema_saude'] = 'Especifique o problema de saúde.'
        if self.usa_medicacao_controlada and not self.medicacao:
            erros['medicacao'] = 'Informe qual medicação.'
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        # Limpa respostas que deixaram de valer.
        if self.tipo_assistencia == self.Assistencia.SUS:
            self.plano_saude = ''
        if not self.possui_problema_saude:
            self.problema_saude = ''
        if not self.usa_medicacao_controlada:
            self.medicacao = self.medicacao_ha_quanto_tempo = self.medicacao_reacoes = ''
        super().save(*args, **kwargs)
