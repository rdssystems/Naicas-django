from django import template

from core.validators import so_digitos

register = template.Library()


@register.filter
def cpf(valor):
    """11 dígitos -> 000.000.000-00 (outros valores passam sem mudança)."""
    d = so_digitos(valor)
    if len(d) != 11:
        return valor
    return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'


@register.filter
def cep(valor):
    d = so_digitos(valor)
    return f'{d[:5]}-{d[5:]}' if len(d) == 8 else valor
