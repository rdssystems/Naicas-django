"""
Anexa PDFs FICTÍCIOS ("DOCUMENTO FICTÍCIO") aos tipos obrigatórios que faltam,
para atendidos de desenvolvimento ficarem com o cadastro completo. Só com DEBUG.

Uso:
    python manage.py popular_anexos --aluno 3 --aluno 4
    python manage.py popular_anexos --ficticios     # atendidos sem criado_por (gerados por popular_alunos)
"""

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from alunos.models import Aluno

from ...etapa import tipos_obrigatorios_pendentes
from ...models import Anexo


def pdf_ficticio(titulo):
    """PDF mínimo válido de 1 página com um texto (sem dependências externas)."""
    texto = f'DOCUMENTO FICTICIO - {titulo}'.encode('latin-1', 'replace').replace(b'(', b'[').replace(b')', b']')
    conteudo = b'BT /F1 14 Tf 50 780 Td (' + texto + b') Tj ET'
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(conteudo)).encode() + b' >>\nstream\n' + conteudo + b'\nendstream',
    ]
    pdf = b'%PDF-1.4\n'
    posicoes = []
    for i, obj in enumerate(objetos, start=1):
        posicoes.append(len(pdf))
        pdf += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(pdf)
    pdf += f'xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n'.encode()
    pdf += b''.join(f'{p:010d} 00000 n \n'.encode() for p in posicoes)
    pdf += f'trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return pdf


class Command(BaseCommand):
    help = 'Anexa PDFs fictícios aos documentos obrigatórios pendentes (desenvolvimento).'

    def add_arguments(self, parser):
        parser.add_argument('--aluno', type=int, action='append', default=[], help='ID do atendido (repetível).')
        parser.add_argument('--ficticios', action='store_true', help='Atendidos sem criado_por (gerados por comando).')

    def handle(self, *args, aluno, ficticios, **options):
        if not settings.DEBUG:
            raise CommandError('Comando de desenvolvimento: só roda com DEBUG=True.')
        if not aluno and not ficticios:
            raise CommandError('Informe --aluno <id> ou --ficticios.')
        alunos = Aluno.objects.filter(pk__in=aluno) if aluno else Aluno.objects.filter(criado_por__isnull=True)

        total = 0
        for registro in alunos:
            for tipo in tipos_obrigatorios_pendentes(registro):
                conteudo = pdf_ficticio(tipo.nome)
                anexo = Anexo(
                    aluno=registro, tipo_documento=tipo, nome_original=f'{tipo.nome} (fictício).pdf',
                    tamanho=len(conteudo),
                )
                anexo.arquivo.save('ficticio.pdf', ContentFile(conteudo), save=True)
                total += 1
        self.stdout.write(self.style.SUCCESS(f'{total} anexos fictícios criados.'))
