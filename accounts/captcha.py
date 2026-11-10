"""
Thamarayyath Employee Portal — Self-Contained Mathematical CAPTCHA Generator.
Built using Pillow. Runs 100% locally with zero external network or API calls,
fully compliant with PythonAnywhere free hosting environment.

Generates arithmetic math challenges (addition, subtraction, multiplication)
rendered into a security image to prevent automated bot access while being
effortless for legitimate human users.
"""

import io
import random
from PIL import Image, ImageDraw, ImageFont


def generate_math_captcha_image(*args, **kwargs) -> tuple[bytes, str]:
    """
    Generate a dynamic mathematical security challenge image and its corresponding answer.
    Returns: (png_bytes, answer_str)
    """
    op = random.choice(["+", "-", "×"])
    if op == "+":
        a = random.randint(3, 25)
        b = random.randint(2, 20)
        ans = a + b
    elif op == "-":
        a = random.randint(12, 35)
        b = random.randint(2, a - 1)
        ans = a - b
    else:  # multiplication
        a = random.randint(2, 9)
        b = random.randint(2, 9)
        ans = a * b

    question_text = f"{a} {op} {b} = ?"
    answer_str = str(ans)

    width, height = 160, 44

    # Background: clean modern light-slate/off-white tint
    bg_color = (
        random.randint(242, 248),
        random.randint(245, 250),
        random.randint(248, 255),
    )
    image = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)

    # 1. Subtle background lines (anti-OCR noise)
    for _ in range(3):
        line_color = (
            random.randint(190, 220),
            random.randint(200, 225),
            random.randint(210, 235),
        )
        x1 = random.randint(0, width // 2)
        y1 = random.randint(0, height)
        x2 = random.randint(width // 2, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=line_color, width=1)

    # 2. Subtle background noise dots
    for _ in range(35):
        dot_color = (
            random.randint(180, 220),
            random.randint(190, 225),
            random.randint(200, 230),
        )
        dx = random.randint(0, width - 1)
        dy = random.randint(0, height - 1)
        draw.point((dx, dy), fill=dot_color)

    # 3. Load font
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:
        font = ImageFont.load_default()

    # Calculate centered position
    bbox = draw.textbbox((0, 0), question_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2 - bbox[0]
    y = (height - text_height) // 2 - bbox[1]

    # Primary colors (Thamarayyath Portal Navy / Teal)
    text_color = random.choice([
        (30, 58, 95),    # Navy
        (15, 118, 110),  # Teal
        (15, 23, 42),    # Deep Slate
        (13, 148, 136),  # Light Teal
    ])

    # Draw text with 1px shadow/emboss for contrast and bold effect
    shadow_color = (205, 215, 225)
    draw.text((x + 1, y + 1), question_text, font=font, fill=shadow_color)
    draw.text((x, y), question_text, font=font, fill=text_color)
    draw.text((x + 0.5, y), question_text, font=font, fill=text_color)

    # 4. Light decorative border
    border_color = (203, 213, 225)
    draw.rectangle([(0, 0), (width - 1, height - 1)], outline=border_color, width=1)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), answer_str


# Backward compatibility alias
generate_captcha_image = generate_math_captcha_image
