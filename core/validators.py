import re

from django.core.exceptions import ValidationError


def so_digitos(valor):
    return re.sub(r'\D', '', valor or '')


def cpf_valido(cpf):
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def validar_cpf(valor):
    if not cpf_valido(valor):
        raise ValidationError('CPF inválido.', code='cpf_invalido')


def validar_cep(valor):
    if len(so_digitos(valor)) != 8:
        raise ValidationError('CEP deve ter 8 dígitos.', code='cep_invalido')


def validar_nis(valor):
    if valor and len(so_digitos(valor)) != 11:
        raise ValidationError('NIS deve ter 11 dígitos.', code='nis_invalido')
