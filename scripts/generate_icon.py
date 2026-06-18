#!/usr/bin/env python3
"""Generate the NetMedic application icon."""
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "assets" / "netmedic.png"


def create_netmedic_icon(path: Path):
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 10
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(26, 35, 126, 255))

    cross_width = 40
    cross_length = 120
    center = size // 2

    draw.rectangle(
        [center - cross_width // 2, center - cross_length // 2,
         center + cross_width // 2, center + cross_length // 2],
        fill=(255, 255, 255, 255),
    )
    draw.rectangle(
        [center - cross_length // 2, center - cross_width // 2,
         center + cross_length // 2, center + cross_width // 2],
        fill=(255, 255, 255, 255),
    )

    green_color = (76, 175, 80, 255)
    arc_margin = 40
    draw.arc([arc_margin, arc_margin, size - arc_margin, size - arc_margin],
             start=225, end=315, fill=green_color, width=12)
    draw.arc([arc_margin + 30, arc_margin + 30, size - arc_margin - 30, size - arc_margin - 30],
             start=225, end=315, fill=green_color, width=10)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    print(f"Icon saved to: {path}")


if __name__ == "__main__":
    create_netmedic_icon(OUTPUT)