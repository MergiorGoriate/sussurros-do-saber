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


def upload_article_image(file, folder=None):
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
        image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
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
            folder=folder or os.getenv("CLOUDINARY_FOLDER", "sussurros-do-saber/artigos"),
            resource_type="image",
            format="webp",
            overwrite=False,
        )
    except CloudinaryError:
        raise ImageUploadError("Não foi possível enviar a imagem ao Cloudinary. Verifique as credenciais.")
    secure_url = result.get("secure_url")
    if not secure_url:
        raise ImageUploadError("O Cloudinary não devolveu o endereço da imagem.")
    return secure_url, result.get("public_id", "")


def delete_article_image(public_id):
    if not public_id:
        return
    required = ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]
    if any(not os.getenv(key) for key in required):
        return
    cloudinary.config(cloud_name=os.environ[required[0]], api_key=os.environ[required[1]], api_secret=os.environ[required[2]], secure=True)
    try:
        cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
    except CloudinaryError:
        pass
