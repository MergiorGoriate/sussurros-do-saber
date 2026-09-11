import io
import os
import uuid
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 8 * 1024 * 1024


class ImageUploadError(ValueError):
    pass


def upload_article_image(file):
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

    required = ["R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_URL"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise ImageUploadError("O Cloudflare R2 ainda não está configurado no Render.")
    key = f"artigos/{uuid.uuid4().hex}.webp"
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    try:
        client.upload_fileobj(output, os.environ["R2_BUCKET"], key, ExtraArgs={"ContentType": "image/webp", "CacheControl": "public, max-age=31536000, immutable"})
    except (BotoCoreError, ClientError):
        raise ImageUploadError("Não foi possível enviar a imagem ao Cloudflare R2. Verifique as credenciais.")
    return f"{os.environ['R2_PUBLIC_URL'].rstrip('/')}/{key}"
