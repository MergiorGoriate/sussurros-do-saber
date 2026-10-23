"""Cover presentation rules; no storage, network calls or publication side effects."""
import os
from urllib.parse import urlsplit, unquote

COVER_MODES = ('image', 'video_animated', 'video_controls')


def effective_cover_mode(mode, video):
    if mode in COVER_MODES:
        return mode
    # Historical covers already supported controlled video before this field existed.
    return 'video_controls' if video else 'image'


def native_video_url(value):
    try:
        url = urlsplit(value or '')
        if (url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password
                or any(c in (value or '') for c in ('\\', '\n', '\r', '\t'))):
            return ''
        return value if url.path.lower().endswith(('.mp4', '.webm', '.ogg')) else ''
    except ValueError:
        return ''


def owned_cloudinary_video(value):
    if not native_video_url(value):
        return False
    url = urlsplit(value)
    cloud = os.getenv('CLOUDINARY_CLOUD_NAME', '').strip()
    if not cloud:
        try:
            cloud = urlsplit(os.getenv('CLOUDINARY_URL', '')).hostname or ''
        except ValueError:
            return False
    path = unquote(url.path)
    return bool(cloud and url.scheme == 'https' and url.netloc == 'res.cloudinary.com'
                and path.startswith('/'+cloud+'/video/upload/') and not url.query and not url.fragment
                and not any(part in {'.', '..'} for part in path.split('/')))


def cover_delivery_url(value, animated=False):
    if owned_cloudinary_video(value):
        options = 'q_auto:good,w_1280,c_limit' + (',ac_none' if animated else '')
        return value.replace('/video/upload/', '/video/upload/'+options+'/', 1)
    return native_video_url(value)


def cover_poster_url(image, video=''):
    """Use the chosen photograph, or a still frame of a public uploaded video.

    This only builds a delivery URL: it never fetches media or changes stored assets.
    """
    def clean(value):
        value = str(value or '').strip()
        if value.startswith('//'):
            value = 'https:' + value
        try:
            url = urlsplit(value)
            if (url.scheme not in {'http', 'https'} or not url.hostname
                    or url.username or url.password
                    or any(c in value for c in ('\\', '\n', '\r', '\t'))):
                return ''
        except ValueError:
            return ''
        return value

    image = clean(image)
    if image and not native_video_url(image):
        return image
    value = clean(video) or image
    if not native_video_url(value):
        return ''
    url = urlsplit(value)
    parts = unquote(url.path).split('/')
    if (url.scheme != 'https' or url.netloc != 'res.cloudinary.com'
            or len(parts) < 6 or parts[2:4] != ['video', 'upload']
            or url.query or url.fragment or any(part in {'.', '..'} for part in parts)):
        return ''
    # An image extension requests a still from the video resource. Keep version,
    # public ID and existing transformations; never alter playback URLs.
    path = url.path.rsplit('.', 1)[0] + '.jpg'
    return url._replace(path=path.replace('/video/upload/', '/video/upload/so_0/', 1)).geturl()
