"""
Thamarayyath Employee Portal — File & Document Compression Engine.

Designed for PythonAnywhere free hosting to strictly stay within the 512 MB disk quota.
Compresses uploaded employee documents (ID cards, certificates, contracts, scans) and
profile photographs by:
1. Stripping heavy EXIF metadata while respecting true orientation.
2. Resizing excessive camera megapixels (e.g. 4000x3000 down to max 1600px for docs, 800px for photos).
3. Re-encoding with high-efficiency JPEG/PNG compression (quality=75-80, optimize=True).
4. Gracefully falling back to the original file if compression does not yield size savings.
"""

import io
import os
import logging
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile

logger = logging.getLogger("portal")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def compress_uploaded_document(uploaded_file, max_dimension: int = 1600, quality: int = 75):
    """
    Compress an uploaded document file.
    If the file is an image (scanned certificate, ID card, document photo),
    resizes to max_dimension and compresses with high efficiency.
    Returns a ContentFile or the original file.
    """
    if not uploaded_file:
        return uploaded_file

    filename = getattr(uploaded_file, "name", "document")
    ext = os.path.splitext(filename)[1].lower()

    if ext not in IMAGE_EXTENSIONS:
        # Non-image files (e.g., PDF, DOCX, XLSX) are already compressed or binary
        return uploaded_file

    return _compress_image_data(
        uploaded_file,
        filename=filename,
        max_dimension=max_dimension,
        quality=quality,
        default_format="JPEG",
    )


def compress_profile_photo(uploaded_file, max_dimension: int = 800, quality: int = 80):
    """
    Compress employee profile photographs (max 800x800, quality 80).
    """
    if not uploaded_file:
        return uploaded_file

    filename = getattr(uploaded_file, "name", "photo.jpg")
    ext = os.path.splitext(filename)[1].lower()

    if ext not in IMAGE_EXTENSIONS:
        return uploaded_file

    return _compress_image_data(
        uploaded_file,
        filename=filename,
        max_dimension=max_dimension,
        quality=quality,
        default_format="JPEG",
    )


def _compress_image_data(
    file_obj,
    filename: str,
    max_dimension: int,
    quality: int,
    default_format: str = "JPEG",
):
    """
    Internal compression helper using Pillow.
    Handles orientation, palette/alpha conversion, resizing, and memory buffering.
    """
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        original_size = getattr(file_obj, "size", 0)
        img = Image.open(file_obj)

        # 1. Correct orientation from EXIF tags before stripping metadata
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # 2. Downscale if dimensions exceed max_dimension
        orig_w, orig_h = img.size
        if orig_w > max_dimension or orig_h > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        # 3. Determine save format & convert modes
        ext = os.path.splitext(filename)[1].lower()
        output_format = "PNG" if ext == ".png" else "JPEG"

        out_buffer = io.BytesIO()

        if output_format == "JPEG":
            # JPEG requires RGB or L mode (convert RGBA / transparency with white bg)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                bg.paste(img, mask=img.split()[-1] if len(img.split()) == 4 else None)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            img.save(out_buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
            # Ensure extension reflects JPEG
            if ext not in [".jpg", ".jpeg"]:
                base = os.path.splitext(filename)[0]
                filename = f"{base}.jpg"
        else:
            # PNG optimization
            img.save(out_buffer, format="PNG", optimize=True, compress_level=9)

        compressed_size = out_buffer.tell()

        # If compressed version is indeed smaller (or original had unknown size), use it
        if original_size == 0 or compressed_size < original_size:
            out_buffer.seek(0)
            compressed_file = ContentFile(out_buffer.read(), name=filename)
            logger.info(
                "Compressed upload '%s': %d bytes -> %d bytes (%.1f%% reduction)",
                filename,
                original_size,
                compressed_size,
                (1 - (compressed_size / original_size)) * 100 if original_size > 0 else 0,
            )
            return compressed_file
        else:
            # Original was already smaller, keep original
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            return file_obj

    except Exception as exc:
        logger.warning("Image compression failed for '%s': %s; using original file.", filename, exc)
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        return file_obj

