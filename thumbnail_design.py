"""Story-led, source-constrained thumbnail art for long videos.

The illustration is a reusable channel character. The only story-specific
numbers come from the caller's already checked hero figure or real candles.
"""
from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DENIZ_ART = Path(__file__).resolve().parent / 'assets/characters/deniz/deniz-editorial-v1.png'
FONT_PATHS = (
    '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
)
INK = '#10192A'
PAPER = '#F3EAD8'
RUST = '#D85432'
CYAN = '#28C6D6'


def _font(size: int):
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fit(draw: ImageDraw.ImageDraw, value: str, width: int, start: int, floor: int = 32):
    size = start
    while size > floor and draw.textlength(value, font=_font(size)) > width:
        size -= 2
    return _font(size)


def _lines(draw: ImageDraw.ImageDraw, words: str, max_width: int, max_lines: int,
           font_size: int) -> list[str]:
    tokens = words.split()
    lines: list[str] = []
    for token in tokens:
        candidate = (lines[-1] + ' ' + token) if lines else token
        if lines and draw.textlength(candidate, font=_font(font_size)) > max_width:
            if len(lines) == max_lines:
                break
            lines.append(token)
        elif lines:
            lines[-1] = candidate
        else:
            lines.append(token)
    return lines[:max_lines]


def _portrait(img: Image.Image, box: tuple[int, int, int, int]) -> None:
    if not DENIZ_ART.exists():
        return
    with Image.open(DENIZ_ART) as source:
        subject = source.convert('RGBA')
        width, height = box[2] - box[0], box[3] - box[1]
        subject.thumbnail((width, height), Image.Resampling.LANCZOS)
        x = box[0] + (width - subject.width) // 2
        y = box[3] - subject.height
        img.alpha_composite(subject, (x, y))


def _texture(img: Image.Image, seed: str, *, light: bool) -> None:
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16))
    layer = Image.new('RGBA', img.size)
    draw = ImageDraw.Draw(layer)
    grain = (16, 25, 42, 18) if light else (246, 238, 219, 22)
    for _ in range(2500):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        draw.point((x, y), fill=grain)
    img.alpha_composite(layer)


def _chart(draw: ImageDraw.ImageDraw, intraday: list[dict], box: tuple[int, int, int, int],
           color: str) -> None:
    closes = [float(row['close']) for row in intraday if row.get('close') is not None]
    if len(closes) < 2:
        raise ValueError('Thumbnail requires at least two real chart closes')
    left, top, right, bottom = box
    low, high = min(closes), max(closes)
    spread = high - low or 1.0
    points = [(left + (right - left) * i / (len(closes) - 1),
               bottom - (bottom - top) * (v - low) / spread) for i, v in enumerate(closes)]
    draw.line(points, fill=color, width=8, joint='curve')
    x, y = points[-1]
    draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=color)


def _family(franchise: str) -> str:
    if franchise in {'congress_trade', 'insider_watch'}:
        return 'FILING'
    if franchise == 'earnings_shock':
        return 'EARNINGS'
    if franchise == 'analyst_shock':
        return 'TARGET'
    return 'MARKET'


def create_story_thumbnail(*, ticker: str, change_pct: str, hook_words: str,
                           intraday: list[dict], output_path: str,
                           franchise: str = '', hero_number: str = '',
                           hero_label: str = '') -> str:
    """Draw one of four distinct poster compositions at 1280x720."""
    family = _family(franchise)
    ticker = re.sub(r'[^A-Za-z0-9.\-]', '', ticker.upper())[:12] or 'STOCK'
    hook = re.sub(r'\s+', ' ', hook_words.upper()).strip()[:80] or 'THE STORY'
    value = hero_number.strip() or f'{change_pct.strip()}%'
    label = (hero_label.strip().upper() if hero_number.strip() else 'SESSION MOVE')[:30]
    light = family in {'FILING', 'TARGET'}
    img = Image.new('RGBA', (1280, 720), PAPER if light else INK)
    draw = ImageDraw.Draw(img)
    _texture(img, ticker + family + hook, light=light)
    draw = ImageDraw.Draw(img)

    if family == 'FILING':
        draw.rectangle((0, 0, 28, 720), fill=RUST)
        draw.rectangle((805, 0, 1280, 720), fill=INK)
        draw.polygon(((750, 0), (820, 0), (710, 720), (640, 720)), fill=RUST)
        _portrait(img, (780, 56, 1275, 720))
        draw.text((70, 48), 'THE FILING  /  US STOCK MARKET DAILY', font=_font(28), fill=INK)
        draw.text((70, 118), ticker, font=_fit(draw, ticker, 590, 135, 72), fill=INK)
        draw.text((74, 287), label, font=_font(28), fill=RUST)
        draw.text((70, 327), value, font=_fit(draw, value, 650, 108, 48), fill=INK)
        for i, line in enumerate(_lines(draw, hook, 630, 2, 48)):
            draw.text((72, 470 + i * 61), line, font=_font(48), fill=INK)
        draw.text((72, 650), 'SOURCE-LED ANALYSIS', font=_font(21), fill=RUST)
    elif family == 'EARNINGS':
        draw.polygon(((0, 0), (650, 0), (490, 720), (0, 720)), fill=RUST)
        _portrait(img, (38, 26, 550, 720))
        draw.text((620, 48), 'EARNINGS  /  US STOCK MARKET DAILY', font=_font(27), fill=CYAN)
        draw.text((610, 105), ticker, font=_fit(draw, ticker, 600, 133, 70), fill=PAPER)
        draw.text((616, 275), label, font=_font(27), fill=CYAN)
        draw.text((610, 312), value, font=_fit(draw, value, 620, 112, 48), fill=PAPER)
        for i, line in enumerate(_lines(draw, hook, 610, 2, 47)):
            draw.text((615, 470 + i * 58), line, font=_font(47), fill=PAPER)
        _chart(draw, intraday, (620, 616, 1190, 672), CYAN)
    elif family == 'TARGET':
        draw.rectangle((0, 0, 1280, 155), fill=CYAN)
        draw.polygon(((735, 155), (1280, 155), (1280, 720), (625, 720)), fill=INK)
        for radius in (260, 185, 110):
            draw.ellipse((1005 - radius, 430 - radius, 1005 + radius, 430 + radius),
                         outline=CYAN if radius == 110 else PAPER, width=8)
        draw.line((760, 430, 1245, 430), fill=RUST, width=7)
        draw.line((1005, 190, 1005, 675), fill=RUST, width=7)
        draw.text((66, 43), 'ANALYST NOTE  /  US STOCK MARKET DAILY', font=_font(28), fill=INK)
        draw.text((62, 187), ticker, font=_fit(draw, ticker, 640, 135, 70), fill=INK)
        draw.text((68, 355), label, font=_font(28), fill=RUST)
        draw.text((62, 394), value, font=_fit(draw, value, 600, 105, 48), fill=INK)
        for i, line in enumerate(_lines(draw, hook, 625, 2, 43)):
            draw.text((66, 548 + i * 52), line, font=_font(43), fill=INK)
    else:
        draw.rectangle((0, 0, 1280, 28), fill=CYAN)
        draw.ellipse((770, -220, 1490, 500), outline=RUST, width=90)
        _portrait(img, (790, 45, 1270, 720))
        draw.text((66, 66), 'THE STORY  /  US STOCK MARKET DAILY', font=_font(27), fill=CYAN)
        draw.text((60, 135), ticker, font=_fit(draw, ticker, 710, 138, 70), fill=PAPER)
        draw.text((66, 316), label, font=_font(28), fill=CYAN)
        draw.text((60, 354), value, font=_fit(draw, value, 720, 113, 48), fill=PAPER)
        for i, line in enumerate(_lines(draw, hook, 720, 2, 45)):
            draw.text((64, 510 + i * 56), line, font=_font(45), fill=PAPER)
        _chart(draw, intraday, (70, 645, 740, 685), CYAN)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.convert('RGB').save(output_path, quality=93)
    return output_path
