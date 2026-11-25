"""Validate catalogue assets without fetching editor-supplied URLs."""
import hashlib
import re
from urllib.parse import parse_qs, unquote, urlsplit

from cover_media import cover_poster_url, native_video_url, owned_cloudinary_video
from premium_resources import safe_url


def https_url(value):
    if any(char.isspace() or char == '\\' or ord(char) < 32 for char in value):
        raise ValueError('Utilize uma ligação HTTPS válida.')
    return safe_url(value)


def media_fields(value, *, legacy=False):
    value = https_url(value)
    parts = urlsplit(value)
    host = (parts.hostname or '').removeprefix('www.')
    path = unquote(parts.path)
    identifier, embed, file_format = '', '', ''
    if owned_cloudinary_video(value):
        resource = path.split('/video/upload/', 1)[1].rsplit('.', 1)[0]
        identifier = re.sub(r'^v\d+/', '', resource)
        if not re.fullmatch(r'[\w.-]+(?:/[\w.-]+)*', identifier) or len(identifier) > 500:
            raise ValueError('Utilize a ligação original do vídeo Cloudinary.')
        key = f'{path.split("/")[1]}:{identifier}'
    elif host in {'youtube.com', 'm.youtube.com', 'youtu.be', 'youtube-nocookie.com'}:
        if host == 'youtu.be':
            code = path.strip('/')
        elif path.startswith('/embed/'):
            code = path.removeprefix('/embed/')
        else:
            code = parse_qs(parts.query).get('v', [''])[0] if path == '/watch' else ''
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', code):
            raise ValueError('Utilize a ligação pública do vídeo no YouTube.')
        embed = key = f'https://www.youtube-nocookie.com/embed/{code}'
    elif host in {'vimeo.com', 'player.vimeo.com'} and re.fullmatch(r'/(?:video/)?\d{5,12}/?', path):
        embed = key = f'https://player.vimeo.com/video/{path.strip("/").split("/")[-1]}'
    elif legacy and native_video_url(value):
        key = value
    else:
        raise ValueError('Utilize um vídeo público da sua Cloudinary, do YouTube ou do Vimeo.')
    if not embed:
        file_format = path.rsplit('.', 1)[-1].lower()
    return dict(url=value, embed_url=embed, format=file_format, cloudinary_id=identifier,
                asset_key=hashlib.sha256(key.encode()).hexdigest())


def article_defaults(article):
    return dict(title=article.title, description=article.summary, keywords=article.keywords or '',
                category_id=article.category_id, author=article.author,
                thumbnail=cover_poster_url(article.image, article.cover_video))


def cloudinary_details(value):
    """Look up a validated first-party asset through the configured Admin API."""
    import os

    import cloudinary.api
    from cloudinary.exceptions import Error as CloudinaryError

    fields = media_fields(value)
    if not fields['cloudinary_id']:
        raise ValueError('Seleccione um vídeo Cloudinary. / Select a Cloudinary video.')
    cloud = urlsplit(value).path.split('/')[1]
    credentials = {key: os.getenv(f'CLOUDINARY_{key.upper()}') for key in ('api_key', 'api_secret')}
    if not all(credentials.values()):
        cloudinary_url = urlsplit(os.getenv('CLOUDINARY_URL', ''))
        credentials = {'api_key': cloudinary_url.username, 'api_secret': cloudinary_url.password}
    if not all(credentials.values()):
        raise ValueError('A API Cloudinary não está configurada. / The Cloudinary API is not configured.')
    try:
        details = cloudinary.api.resource(fields['cloudinary_id'], resource_type='video', type='upload',
                                          cloud_name=cloud, timeout=8, **credentials)
        return dict(duration=max(1, round(float(details['duration']))),
                    width=int(details['width']), height=int(details['height']))
    except (CloudinaryError, OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        raise ValueError('Metadados Cloudinary indisponíveis. / Cloudinary metadata unavailable.') from error
