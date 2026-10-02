"""Validação de anexos: extensão, tamanho e CONTEÚDO (não confia só no nome do arquivo)."""

import os

from django.core.exceptions import ValidationError
from PIL import Image

TAMANHO_MAXIMO = 10 * 1024 * 1024  # 10 MB

# extensão -> (content-type, formato do Pillow ou None para PDF)
FORMATOS = {
    'pdf': ('application/pdf', None),
    'jpg': ('image/jpeg', 'JPEG'),
    'jpeg': ('image/jpeg', 'JPEG'),
    'png': ('image/png', 'PNG'),
    'webp': ('image/webp', 'WEBP'),
}
EXTENSOES_ACEITAS = ', '.join(sorted({e.upper() for e in FORMATOS} - {'JPEG'}))


def extensao(nome):
    return os.path.splitext(nome)[1].lower().lstrip('.')


def validar_arquivo(arquivo):
    """Levanta ValidationError se o arquivo não for imagem/PDF válido de até 10 MB."""
    ext = extensao(arquivo.name)
    if ext not in FORMATOS:
        raise ValidationError(f'Formato não aceito. Envie {EXTENSOES_ACEITAS}.')
    if arquivo.size > TAMANHO_MAXIMO:
        raise ValidationError('Arquivo maior que 10 MB.')

    _, formato_imagem = FORMATOS[ext]
    arquivo.seek(0)
    try:
        if formato_imagem is None:
            if not arquivo.read(5).startswith(b'%PDF-'):
                raise ValidationError('O arquivo não é um PDF válido.')
        else:
            imagem = Image.open(arquivo)
            if imagem.format != formato_imagem:
                raise ValidationError('O conteúdo da imagem não corresponde à extensão do arquivo.')
            imagem.verify()
    except ValidationError:
        raise
    except Exception:
        raise ValidationError('Não foi possível ler o arquivo. Ele pode estar corrompido.')
    finally:
        arquivo.seek(0)
