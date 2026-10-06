import io
import os
import uuid
import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 8 * 1024 * 1024


class ImageUploadError(ValueError):
    pass


def _upload_image(file, *, folder, max_dimensions):
    if not file or not file.filename:
        return None
    payload = file.read(MAX_IMAGE_BYTES + 1)
    if len(payload) > MAX_IMAGE_BYTES:
        raise ImageUploadError("A imagem deve ter no máximo 8 MB.")
    try:
        image = Image.open(io.BytesIO(payload))
        image.verify()
        image = Image.open(io.BytesIO(payload))
        if image.width * image.height > 40_000_000:
            raise ImageUploadError("A imagem possui resolução demasiado elevada.")
        image.thumbnail(max_dimensions, Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, "WEBP", quality=84, method=6)
        output.seek(0)
    except (UnidentifiedImageError, OSError):
        raise ImageUploadError("O arquivo enviado não é uma imagem válida.")

    required = ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise ImageUploadError("O Cloudinary ainda não está configurado no Render.")
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    try:
        result = cloudinary.uploader.upload(
            output,
            public_id=uuid.uuid4().hex,
            folder=folder,
            resource_type="image",
            format="webp",
            overwrite=False,
        )
    except CloudinaryError:
        raise ImageUploadError("Não foi possível enviar a imagem ao Cloudinary. Verifique as credenciais.")
    secure_url = result.get("secure_url")
    if not secure_url:
        raise ImageUploadError("O Cloudinary não devolveu o endereço da imagem.")
    return secure_url



def upload_article_image(file):
    return _upload_image(
        file,
        folder=os.getenv("CLOUDINARY_FOLDER", "sussurros-do-saber/artigos"),
        max_dimensions=(2000, 2000),
    )


def upload_author_photo(file):
    return _upload_image(
        file,
        folder=os.getenv("CLOUDINARY_AUTHOR_FOLDER", "sussurros-do-saber/autores"),
        max_dimensions=(800, 800),
    )



def upload_journal_cover(file):
    return _upload_image(
        file,
        folder=os.getenv("CLOUDINARY_JOURNAL_FOLDER", "sussurros-do-saber/revistas"),
        max_dimensions=(1600, 2200),
    )


MAX_VIDEO_BYTES = 50 * 1024 * 1024


class VideoUploadError(ValueError):
    pass


def upload_article_video(file):
    if not file or not file.filename:
        raise VideoUploadError("Seleccione um vídeo para carregar.")
    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in {".mp4", ".webm", ".ogg"}:
        raise VideoUploadError("Use um vídeo MP4, WebM ou OGG.")
    payload = file.read(MAX_VIDEO_BYTES + 1)
    if not payload or len(payload) > MAX_VIDEO_BYTES:
        raise VideoUploadError("O vídeo deve ter entre 1 byte e 50 MB.")
    valid = (
        (extension == ".mp4" and len(payload) >= 12 and payload[4:8] == b"ftyp")
        or (extension == ".webm" and payload.startswith(b"\x1a\x45\xdf\xa3"))
        or (extension == ".ogg" and payload.startswith(b"OggS"))
    )
    if not valid:
        raise VideoUploadError("O ficheiro não corresponde ao formato de vídeo seleccionado.")
    if not all(os.getenv(key) for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")):
        raise VideoUploadError("O armazenamento de vídeos ainda não está configurado.")
    cloudinary.config(cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
                      api_key=os.environ["CLOUDINARY_API_KEY"],
                      api_secret=os.environ["CLOUDINARY_API_SECRET"], secure=True)
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(payload), resource_type="video", format="mp4",
            public_id=uuid.uuid4().hex,
            folder=os.getenv("CLOUDINARY_VIDEO_FOLDER", "sussurros-do-saber/videos"),
            overwrite=False, timeout=120,
        )
    except CloudinaryError as error:
        raise VideoUploadError("Não foi possível carregar o vídeo. Tente novamente.") from error
    if not result.get("secure_url"):
        raise VideoUploadError("O armazenamento não devolveu o endereço do vídeo.")
    return result["secure_url"]
