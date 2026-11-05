"""1080x1920 프레임(PNG) 렌더링."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
MARGIN = 60

THEMES = {
    "economy":     ("#19C37D", "경제"),
    "stock":       ("#F5B700", "재테크"),
    "realestate":  ("#F97316", "부동산"),
    "policy":      ("#8B5CF6", "정책·지원금"),
    "it":          ("#3B82F6", "IT·테크"),
    "health":      ("#14B8A6", "건강"),
    "car":         ("#06B6D4", "자동차"),
    "society":     ("#EF4444", "사회"),
    "entertainment": ("#EC4899", "연예"),
    "sports":      ("#22C55E", "스포츠"),
}
DEFAULT_THEME = ("#EF4444", "이슈")
SUB_HIGHLIGHT = "#FFE14D"

_NON_BMP = re.compile(r"[\U00010000-\U0010FFFF☀-➿️]")


def clean(text: str) -> str:
    """폰트에 없는 이모지 제거(네모 깨짐 방지)."""
    return _NON_BMP.sub("", text or "").strip()


def theme(category: str) -> tuple[str, str]:
    return THEMES.get((category or "").lower(), DEFAULT_THEME)


@lru_cache(maxsize=64)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- 줄바꿈
def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int, info: dict | None = None) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        # 단어 하나가 너무 길면 글자 단위로 자른다
        cur = ""
        for ch in word:
            if f.getlength(cur + ch) > max_w and cur:
                if info is not None:
                    info["broke"] = True
                lines.append(cur)
                cur = ch
            else:
                cur += ch
    if cur:
        lines.append(cur)
    return lines


def fit(text: str, path: str, max_w: int, max_lines: int, start: int, minimum: int):
    size = start
    while size > minimum:
        f = font(path, size)
        info: dict = {}
        lines = wrap(text, f, max_w, info)
        if len(lines) <= max_lines and not info.get("broke"):
            return f, lines
        size -= 4
    f = font(path, minimum)
    lines = wrap(text, f, max_w)
    if len(lines) > max_lines:  # 그래도 넘치면 말줄임
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "…"
    return f, lines


def _hl_mask(line: str, highlights: list[str]) -> list[bool]:
    """줄 안에서 강조어가 차지하는 글자 위치 표시 (여러 단어 강조어 지원)."""
    mask = [False] * len(line)
    for h in highlights:
        h = (h or "").strip()
        if not h:
            continue
        start = line.find(h)
        while start != -1:
            for j in range(start, start + len(h)):
                mask[j] = True
            start = line.find(h, start + 1)
    return mask


def draw_words(d: ImageDraw.ImageDraw, lines, f, center_x, top, line_h, color, hl_color,
               highlights, stroke=0, stroke_fill="#000000"):
    space = f.getlength(" ")
    for i, line in enumerate(lines):
        words = line.split(" ")
        total = sum(f.getlength(w) for w in words) + space * (len(words) - 1)
        x = center_x - total / 2
        y = top + i * line_h
        mask = _hl_mask(line, highlights)
        pos = 0
        for w in words:
            c = hl_color if any(mask[pos:pos + len(w)]) else color
            d.text((x, y), w, font=f, fill=c, stroke_width=stroke, stroke_fill=stroke_fill)
            x += f.getlength(w) + space
            pos += len(w) + 1


# ---------------------------------------------------------------- 배경
@lru_cache(maxsize=16)
def background(accent: str) -> Image.Image:
    ar, ag, ab = _rgb(accent)
    top = (int(ar * 0.16) + 8, int(ag * 0.16) + 8, int(ab * 0.16) + 12)
    bot = (6, 7, 10)
    t = np.linspace(0, 1, H)[:, None, None]
    grad = np.array(top)[None, None, :] * (1 - t) + np.array(bot)[None, None, :] * t
    img = Image.fromarray(np.repeat(grad, W, axis=1).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(0, W, 90):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 9), width=1)
    for y in range(0, H, 90):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 9), width=1)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([140, 560, 940, 1200], fill=(ar, ag, ab, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    img.paste(glow, (0, 0), glow)
    return img


@lru_cache(maxsize=32)
def load_image(path: str, box_w: int, box_h: int) -> Image.Image | None:
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im).convert("RGB")
        return ImageOps.fit(im, (box_w, box_h), Image.LANCZOS)
    except Exception:
        return None


# ---------------------------------------------------------------- 프레임
CARD = (MARGIN, 600, W - MARGIN, 1190)
SUB_TOP = 1260


def render_frame(out: Path, *, font_path: str, script: dict, scene: dict, sub_lines_text: str,
                 progress: float, channel: str, image_path: str | None) -> None:
    accent, label = theme(script.get("category", ""))
    badge = clean(script.get("badge") or label)
    img = background(accent).copy()
    d = ImageDraw.Draw(img, "RGBA")
    ar, ag, ab = _rgb(accent)

    # 진행 바
    d.rectangle([0, 0, W, 12], fill=(255, 255, 255, 30))
    d.rectangle([0, 0, int(W * max(0.0, min(1.0, progress))), 12], fill=accent)

    # 워터마크 (오른쪽 위)
    if channel:
        wf = font(font_path, 38)
        tw = wf.getlength(channel)
        x1, y1 = W - MARGIN, 64
        d.rounded_rectangle([x1 - tw - 36, y1 - 6, x1, y1 + 54], radius=28, fill=(0, 0, 0, 110))
        d.text((x1 - tw - 18, y1 + 2), channel, font=wf, fill=(255, 255, 255, 215))

    # 배지 + 제목
    bf = font(font_path, 42)
    bw = bf.getlength(badge)
    d.rounded_rectangle([MARGIN, 160, MARGIN + bw + 48, 226], radius=14, fill=accent)
    d.text((MARGIN + 24, 168), badge, font=bf, fill="#FFFFFF")
    tf, tlines = fit(clean(script["title"]), font_path, W - 2 * MARGIN, 2, 86, 60)
    th = tf.size + 18
    for i, line in enumerate(tlines):
        y = 262 + i * th
        lw = tf.getlength(line)
        d.rectangle([MARGIN, y + tf.size * 0.62, MARGIN + lw, y + tf.size + 6], fill=(ar, ag, ab, 120))
        d.text((MARGIN, y), line, font=tf, fill="#FFFFFF")

    # 카드
    cx1, cy1, cx2, cy2 = CARD
    caption = clean(scene.get("caption", ""))
    highlights = [clean(h) for h in scene.get("highlight", [])]
    pic = load_image(image_path, cx2 - cx1, cy2 - cy1) if image_path else None
    if pic is not None:
        mask = Image.new("L", pic.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, *pic.size], radius=36, fill=255)
        img.paste(pic, (cx1, cy1), mask)
        shade = Image.new("RGBA", pic.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shade)
        for i in range(pic.size[1] // 2):
            a = int(200 * i / (pic.size[1] / 2))
            sd.line([(0, pic.size[1] // 2 + i), (pic.size[0], pic.size[1] // 2 + i)], fill=(0, 0, 0, a))
        img.paste(shade, (cx1, cy1), Image.composite(shade, Image.new("RGBA", pic.size), mask))
        d = ImageDraw.Draw(img, "RGBA")
        if caption:
            cf, clines = fit(caption, font_path, cx2 - cx1 - 80, 2, 84, 52)
            lh = cf.size + 14
            top = cy2 - 40 - lh * len(clines)
            draw_words(d, clines, cf, (cx1 + cx2) / 2, top, lh, "#FFFFFF", accent, highlights,
                       stroke=3, stroke_fill="#000000")
        credit = clean(scene.get("image_credit", ""))
        if credit:
            sf = font(font_path, 26)
            d.text((cx2 - 20 - sf.getlength(credit), cy1 + 16), credit, font=sf, fill=(255, 255, 255, 170))
    else:
        d.rounded_rectangle(CARD, radius=36, fill=(255, 255, 255, 14), outline=(ar, ag, ab, 150), width=4)
        if caption:
            cf, clines = fit(caption, font_path, cx2 - cx1 - 100, 3, 150, 64)
            lh = int(cf.size * 1.22)
            top = (cy1 + cy2) / 2 - lh * len(clines) / 2 - cf.size * 0.08
            draw_words(d, clines, cf, (cx1 + cx2) / 2, top, lh, "#FFFFFF", accent, highlights)

    # 자막
    if sub_lines_text:
        sf, slines = fit(sub_lines_text, font_path, W - 2 * MARGIN - 20, 2, 76, 56)
        lh = sf.size + 20
        draw_words(d, slines, sf, W / 2, SUB_TOP, lh, "#FFFFFF", SUB_HIGHLIGHT, highlights,
                   stroke=7, stroke_fill="#000000")

    # 출처
    src = clean(scene.get("source") or script.get("source_label", ""))
    if src:
        sf = font(font_path, 30)
        text = f"출처: {src}"
        d.text(((W - sf.getlength(text)) / 2, 1520), text, font=sf, fill=(255, 255, 255, 140))

    img.save(out, "PNG", compress_level=1)
