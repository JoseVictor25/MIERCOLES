"""Archivos de imagen privados de los mensajes del chat."""

import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"),
           "WEBP": ("webp", "image/webp"), "GIF": ("gif", "image/gif")}


def private_path(relative):
    """Resuelve una ruta interna sin permitir que salga del directorio privado."""
    root = Path(settings.CHAT_IMAGE_ROOT).resolve()
    path = (root / str(relative or "")).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Ruta de imagen no válida.")
    return path


def save_image(uploaded, project_id):
    """Valida el contenido real y conserva el original con una miniatura ligera."""
    if uploaded.size > MAX_IMAGE_BYTES:
        raise ValueError("La imagen supera el límite de 8 MB.")
    content = uploaded.read()
    if not content:
        raise ValueError("La imagen está vacía.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image_format = image.format
            if image_format not in FORMATS:
                raise ValueError("Usa una imagen PNG, JPG, WEBP o GIF.")
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError("La imagen tiene demasiados píxeles.")
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.seek(0)
            preview = ImageOps.exif_transpose(image).convert("RGBA")
            white = Image.new("RGBA", preview.size, "white")
            white.alpha_composite(preview)
            thumbnail = white.convert("RGB")
            thumbnail.thumbnail((800, 800))
            output = io.BytesIO()
            thumbnail.save(output, format="JPEG", quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("El archivo no es una imagen válida.") from exc

    extension, mime = FORMATS[image_format]
    token = uuid.uuid4().hex
    original_name = f"{project_id}/{token}.{extension}"
    thumbnail_name = f"{project_id}/{token}_mini.jpg"
    original_path = private_path(original_name)
    thumbnail_path = private_path(thumbnail_name)
    original_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        original_path.write_bytes(content)
        thumbnail_path.write_bytes(output.getvalue())
    except OSError:
        original_path.unlink(missing_ok=True)
        thumbnail_path.unlink(missing_ok=True)
        raise
    return {"image_path": original_name, "thumbnail_path": thumbnail_name,
            "mime_type": mime, "width": width, "height": height,
            "size_bytes": len(content)}


def delete_image(meta):
    """Borra los archivos asociados cuando se elimina el mensaje."""
    for key in ("image_path", "thumbnail_path"):
        if meta.get(key):
            try:
                private_path(meta[key]).unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
