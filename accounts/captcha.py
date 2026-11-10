"""
Thamarayyath Employee Portal — Self-Contained Offline CAPTCHA Generator.
Built using Pillow. Runs 100% locally with zero external network or API calls,
fully compliant with PythonAnywhere free hosting environment.
"""

import io
import random
from PIL import Image, ImageDraw, ImageFont

# Exclude easily confused characters (0, O, 1, I, L)
CAPTCHA_CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_captcha_image(length: int = 5) -> tuple[bytes, str]:
    """
    Generate a dynamic security challenge image and its corresponding answer.
    Returns: (png_bytes, code_str)
    """
    code = "".join(random.choices(CAPTCHA_CHARS, k=length))
    width, height = 150, 44

    # Background with slight gradient/tint
    bg_color = (random.randint(238, 246), random.randint(242, 250), random.randint(246, 255))
    image = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)

    # 1. Background noise: random interference lines
    for _ in range(5):
        line_color = (
            random.randint(140, 200),
            random.randint(150, 210),
            random.randint(160, 220),
        )
        x1 = random.randint(0, width // 3)
        y1 = random.randint(0, height)
        x2 = random.randint(width // 2, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=line_color, width=1)

    # 2. Background noise: small dots
    for _ in range(60):
        dot_color = (
            random.randint(160, 220),
            random.randint(170, 220),
            random.randint(180, 230),
        )
        dx = random.randint(0, width - 1)
        dy = random.randint(0, height - 1)
        draw.point((dx, dy), fill=dot_color)

    # 3. Draw text characters with varied colors and positioning
    # Colors: Navy, Teal, Charcoal
    char_colors = [
        (30, 58, 95),    # Navy
        (15, 118, 110),  # Teal
        (51, 65, 85),    # Slate
        (13, 148, 136),  # Light Teal
        (15, 23, 42),    # Deep Slate
    ]

    char_spacing = (width - 24) / length
    for i, char in enumerate(code):
        x = int(12 + (i * char_spacing) + random.randint(-2, 2))
        y = random.randint(6, 12)
        color = random.choice(char_colors)

        # Draw character directly
        draw.text((x, y), char, fill=color)
        # Boldening offset
        draw.text((x + 1, y), char, fill=color)

    # 4. Foreground cross-hatch line
    draw.line(
        [(0, random.randint(10, height - 10)), (width, random.randint(10, height - 10))],
        fill=(15, 118, 110, 100),
        width=1,
    )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), code
