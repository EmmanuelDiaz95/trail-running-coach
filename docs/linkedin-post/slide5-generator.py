"""LinkedIn carousel slide 5 — stack list. Vertical layout, no overflow."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1080
BG = (12, 12, 14)
TEXT = (224, 220, 214)
DIM = (140, 134, 128)
ACCENT = (199, 114, 70)

OUT = Path(__file__).parent / "slide5.png"

mono_candidates = [
    "/Library/Fonts/IBM Plex Mono.ttf",
    "/Users/emmanueldiaz/Library/Fonts/IBMPlexMono-Regular.ttf",
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
]
font_path = next((p for p in mono_candidates if Path(p).exists()), "/System/Library/Fonts/Menlo.ttc")
print(f"Using font: {font_path}")

eyebrow_font = ImageFont.truetype(font_path, 28)
stack_font = ImageFont.truetype(font_path, 56)
hero_font = ImageFont.truetype(font_path, 56)
caption_font = ImageFont.truetype(font_path, 26)

img = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

# Top accent
draw.rectangle([(0, 0), (W, 4)], fill=ACCENT)

# Eyebrow
draw.text((W / 2, 130), "BUILT WITH", font=eyebrow_font, fill=ACCENT, anchor="mm")

# Vertical stack list
stack = ["Python", "FastAPI", "Postgres", "Next.js", "Garmin Connect"]
y = 220
line_height = 78
for item in stack:
    draw.text((W / 2, y), item, font=stack_font, fill=TEXT, anchor="mm")
    y += line_height

# Hero line — Anthropic Claude in copper
y += 8
draw.text((W / 2, y), "Anthropic Claude", font=hero_font, fill=ACCENT, anchor="mm")

# Divider
y += 80
draw.line([(W / 2 - 80, y), (W / 2 + 80, y)], fill=ACCENT, width=2)

# Captions
y += 50
draw.text((W / 2, y), "Solo build · Claude Code", font=caption_font, fill=DIM, anchor="mm")
y += 38
draw.text((W / 2, y), "~30 days idea to production", font=caption_font, fill=DIM, anchor="mm")

img.save(OUT)
print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
