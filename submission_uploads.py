"""Bounded, non-executable manuscript uploads and safe DOCX import."""
import csv
import hashlib
import io
import re
import secrets
import zipfile
from xml.etree import ElementTree as ET
from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from werkzeug.utils import secure_filename

MAX_FILE = 8 * 1024 * 1024
MIMES = {'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
         'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         'pdf': 'application/pdf', 'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
         'csv': 'text/csv', 'txt': 'text/plain'}
KINDS = {'main': 'Manuscrito principal', 'figure': 'Figura', 'table': 'Tabela',
         'supplement': 'Material suplementar', 'data': 'Dados suplementares', 'other': 'Outro documento'}

def office_archive(data, ext):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(infos) > 1500 or sum(item.file_size for item in infos) > 32 * 1024 * 1024:
            raise ValueError('Documento comprimido demasiado grande.')
        if len(set(names)) != len(names) or any(item.flag_bits & 1 or item.filename.startswith('/') or '..' in item.filename.split('/') for item in infos):
            raise ValueError('Estrutura do documento inválida.')
        required = 'word/document.xml' if ext == 'docx' else 'xl/workbook.xml'
        if '[Content_Types].xml' not in names or required not in names:
            raise ValueError('O documento não corresponde ao formato indicado.')
        if any('vba' in name.lower() or 'embeddings/' in name.lower() or 'activex/' in name.lower() for name in names):
            raise ValueError('Macros e objetos executáveis não são permitidos.')
        for item in infos:
            if item.filename.endswith(('.xml', '.rels')):
                value = archive.read(item)
                if b'<!DOCTYPE' in value.upper() or b'<!ENTITY' in value.upper():
                    raise ValueError('XML com entidades não é permitido.')
                ET.fromstring(value)
                if item.filename.endswith('.rels'):
                    for relation in ET.fromstring(value):
                        if relation.get('TargetMode') == 'External':
                            from urllib.parse import urlparse
                            if not relation.get('Type','').endswith('/hyperlink') or urlparse(relation.get('Target','')).scheme not in ('https','http','mailto'):
                                raise ValueError('Remova objetos externos incorporados do documento.')
        main_xml = ET.fromstring(archive.read(required))
        expected_tag = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document' if ext == 'docx' else '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook'
        if main_xml.tag != expected_tag:
            raise ValueError('Estrutura interna incompatível com o formato do documento.')
        if archive.testzip():
            raise ValueError('Documento corrompido.')
        return archive
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, KeyError) as error:
        raise ValueError('Documento inválido ou corrompido.') from error

def validate_upload(upload, kind, main_formats):
    if kind not in KINDS:
        raise ValueError('Selecione uma categoria válida para o ficheiro.')
    name = secure_filename(upload.filename or '')[:180]
    ext = name.rsplit('.', 1)[-1].lower()
    allowed = set(main_formats.split(',')) if kind == 'main' else set(MIMES)
    if ext not in MIMES or ext not in allowed:
        raise ValueError('Formato não autorizado para este ficheiro.')
    data = upload.stream.read(MAX_FILE + 1)
    if not data or len(data) > MAX_FILE:
        raise ValueError('Cada ficheiro deve ter conteúdo e no máximo 8 MB.')
    mime = MIMES[ext]
    if upload.mimetype not in ('application/octet-stream', mime, 'application/zip' if ext in ('docx', 'xlsx') else mime):
        raise ValueError('O tipo MIME não corresponde ao formato do ficheiro.')
    if ext in ('docx', 'xlsx'):
        office_archive(data, ext).close()
    elif ext == 'pdf':
        if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]:
            raise ValueError('PDF inválido ou incompleto.')
        if re.search(rb'/(JavaScript|JS|Launch|EmbeddedFile|RichMedia|OpenAction)\b', data):
            raise ValueError('PDF com conteúdo ativo não é permitido.')
        try:
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 500:
                raise ValueError('Envie um PDF não cifrado com até 500 páginas.')
            root = reader.trailer['/Root']
            names = root.get('/Names', {})
            if hasattr(names, 'get_object'):
                names = names.get_object()
            if any(key in root for key in ('/OpenAction', '/AA')) or '/JavaScript' in names:
                raise ValueError('PDF com ações automáticas não é permitido.')
            for page in reader.pages:
                for annotation in page.get('/Annots', []):
                    value = annotation.get_object()
                    action = value.get('/A')
                    if value.get('/AA') or (action and action.get_object().get('/S') not in ('/URI', '/GoTo')):
                        raise ValueError('PDF com ações não autorizadas.')
        except (PdfReadError, KeyError, TypeError, RecursionError) as error:
            raise ValueError('PDF corrompido ou inválido.') from error
    elif ext in ('png', 'jpg', 'jpeg'):
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != ('PNG' if ext == 'png' else 'JPEG') or image.width * image.height > 20000000:
                    raise ValueError('Imagem inválida ou demasiado grande.')
                image.verify()
        except (OSError, Image.DecompressionBombError) as error:
            raise ValueError('Imagem corrompida.') from error
    else:
        try:
            value = data.decode('utf-8-sig')
            if '\x00' in value or any(ord(char) < 32 and char not in '\n\r\t' for char in value):
                raise ValueError('Texto com caracteres inválidos.')
            if ext == 'csv':
                list(csv.reader(io.StringIO(value)))
        except (UnicodeError, csv.Error) as error:
            raise ValueError('Envie texto em UTF-8.') from error
    return dict(original_name=name, internal_name=secrets.token_hex(24) + '.' + ext,
                mime=mime, size=len(data), sha256=hashlib.sha256(data).hexdigest(), payload=data, kind=kind)

def docx_markdown(data):
    """Import text and table cells, leaving final layout to the existing journal editor."""
    with office_archive(data, 'docx') as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    result = []
    body = root.find('w:body', ns)
    for node in body if body is not None else []:
        if node.tag.endswith('}p'):
            value = ''.join(node.itertext()) if not node.findall('.//w:t', ns) else ''.join(item.text or '' for item in node.findall('.//w:t', ns))
            if value.strip():
                result.append(value.replace('<', '&lt;').replace('>', '&gt;'))
        elif node.tag.endswith('}tbl'):
            rows = [[' '.join(item.text or '' for item in cell.findall('.//w:t', ns)).replace('|', '\\|')
                     for cell in row.findall('w:tc', ns)] for row in node.findall('w:tr', ns)]
            if rows and rows[0]:
                count = max(map(len, rows))
                rows = [row + [''] * (count - len(row)) for row in rows]
                result.append('\n'.join(['| ' + ' | '.join(rows[0]) + ' |', '| ' + ' | '.join(['---'] * count) + ' |'] +
                                        ['| ' + ' | '.join(row) + ' |' for row in rows[1:]]))
    return '\n\n'.join(result)[:400000]
