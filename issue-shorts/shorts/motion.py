"""움직이는 쇼츠 렌더러 (style: motion).

장면 종류(layout)
  hook   : 첫 장면. 노란 집중선 + 거대한 글씨 + 스티커 (썸네일 역할)
  text   : 핵심 문구가 튀어나옴
  point  : ①②③ 번호 + 문구
  number : 숫자 카운트업 + 증감 배지
  vs     : 좌우 대결 (VS 쾅)
  image  : 직접 넣은 이미지 + 천천히 확대
  cta    : 마지막. 정리 + 구독 버튼
"""
from __future__ import annotations

import math
import random
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import render
from .config import ASSETS

W, H = 1080, 1920
FPS = 30
YEL, RED, BLUE, WHITE, BLACK = (255, 230, 0), (255, 59, 48), (47, 123, 255), (255, 255, 255), (0, 0, 0)
HOOK_BG = (255, 214, 10)
CENTER_Y = 890
SUB_Y = 1300


# ================================================================ 폰트·글자
class Fonts:
    def __init__(self, font_path: str):
        black = ASSETS / "fonts" / "Pretendard-Black.otf"
        self.heavy = str(black) if black.exists() else font_path
        self.bold = font_path

    @staticmethod
    @lru_cache(maxsize=128)
    def get(path: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(path, size)

    def H(self, size):
        return self.get(self.heavy, size)

    def B(self, size):
        return self.get(self.bold, size)


def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def segments(line: str, highlights, base, hl):
    """한 줄을 (글자, 색) 조각으로. 강조어는 hl 색."""
    mask = render._hl_mask(line, highlights)
    segs, cur, cur_hl = [], "", None
    for ch, m in zip(line, mask):
        if cur_hl is None or m == cur_hl:
            cur += ch
        else:
            segs.append((cur, hl if cur_hl else base))
            cur = ch
        cur_hl = m
    if cur:
        segs.append((cur, hl if cur_hl else base))
    return segs


def text_layer(lines_segs, f, stroke=0, sf=BLACK, shadow=None, line_gap=1.12, align="center"):
    """여러 줄(색 조각) → 투명 레이어."""
    pad = stroke + (max(abs(shadow[0]), abs(shadow[1])) if shadow else 0) + 6
    widths = [sum(f.getlength(t) for t, _ in segs) for segs in lines_segs]
    lh = int(f.size * line_gap)
    w = int(max(widths or [1])) + pad * 2
    h = lh * len(lines_segs) + int(f.size * 0.3) + pad * 2
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, segs in enumerate(lines_segs):
        x = pad + ((w - 2 * pad - widths[i]) / 2 if align == "center" else 0)
        y = pad + i * lh
        for t, c in segs:
            if shadow:
                d.text((x + shadow[0], y + shadow[1]), t, font=f, fill=shadow[2],
                       stroke_width=stroke, stroke_fill=shadow[2])
            d.text((x, y), t, font=f, fill=c, stroke_width=stroke, stroke_fill=sf)
            x += f.getlength(t)
    return layer


def wrap_fit(text, font_fn, max_w, max_lines, start, minimum):
    size = start
    while size > minimum:
        f = font_fn(size)
        info = {}
        lines = render.wrap(text, f, max_w, info)
        if len(lines) <= max_lines and not info.get("broke"):
            return f, lines
        size -= 6
    f = font_fn(minimum)
    return f, render.wrap(text, f, max_w)[:max_lines]


# ================================================================ 애니메이션 도우미
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease_out_back(x):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_out(x):
    return 1 - (1 - x) ** 3


def pop(t, start, dur=0.22, from_scale=0.4):
    x = clamp((t - start) / dur)
    return from_scale + (1 - from_scale) * ease_out_back(x), clamp(x * 3)


def paste(base: Image.Image, layer: Image.Image, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    if alpha <= 0.01 or scale <= 0.01:
        return
    im = layer
    if angle:
        im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
    if abs(scale - 1) > 0.004:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if alpha < 0.99:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    base.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


# ================================================================ 배경
@lru_cache(maxsize=8)
def body_bg(accent: tuple) -> Image.Image:
    top = tuple(int(c * 0.10) + 6 for c in accent)
    bot = (4, 5, 9)
    t = np.linspace(0, 1, H)[:, None, None]
    grad = np.array(top)[None, None, :] * (1 - t) + np.array(bot)[None, None, :] * t
    img = Image.fromarray(np.repeat(grad, W + 160, axis=1).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(-H, W + 160, 80):  # 사선 줄무늬 (가로로 흘러감)
        d.line([(x, 0), (x + H, H)], fill=(255, 255, 255, 10), width=26)
    return img


def burst(t, color=HOOK_BG, rays=22):
    img = Image.new("RGB", (W, H), color)
    d = ImageDraw.Draw(img)
    cx, cy = W / 2, 820
    rot = t * 0.18
    light = tuple(min(255, int(c + (255 - c) * 0.45)) for c in color)
    for i in range(rays):
        a1 = rot + math.pi * 2 * i / rays
        a2 = a1 + math.pi / rays
        d.polygon([(cx, cy), (cx + 2400 * math.cos(a1), cy + 2400 * math.sin(a1)),
                   (cx + 2400 * math.cos(a2), cy + 2400 * math.sin(a2))], fill=light)
    return img


# ================================================================ 부품
def sticker_layer(fonts, text, color, r=125):
    size = r * 2 + 30
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = size / 2
    pts = [(c + (r if i % 2 == 0 else r * 0.88) * math.cos(math.pi * 2 * i / 36),
            c + (r if i % 2 == 0 else r * 0.88) * math.sin(math.pi * 2 * i / 36)) for i in range(36)]
    d.polygon(pts, fill=color, outline=WHITE, width=6)
    f, lines = wrap_fit(text, fonts.H, int(r * 1.5), 2, int(r * 0.55), int(r * 0.3))
    tl = text_layer([[(ln, WHITE)] for ln in lines], f)
    layer.paste(tl, (int(c - tl.width / 2), int(c - tl.height / 2)), tl)
    return layer


def subtitle_layer(fonts, text, highlights, boxed=False):
    f, lines = wrap_fit(text, fonts.H, 900, 2, 84 if not boxed else 76, 58)
    segs = [segments(ln, highlights, WHITE, YEL) for ln in lines]
    if not boxed:
        return text_layer(segs, f, stroke=9)
    tl = text_layer(segs, f)
    box = Image.new("RGBA", (920, max(180, tl.height + 50)), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle([0, 0, box.width - 1, box.height - 1], radius=32, fill=(0, 0, 0, 235))
    box.paste(tl, (int((box.width - tl.width) / 2), int((box.height - tl.height) / 2)), tl)
    return box


def headline_layer(fonts, script, accent):
    """본문 장면 상단에 고정되는 2줄 제목 + 배지."""
    layer = Image.new("RGBA", (W, 520), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, 0, W, 520], fill=(0, 0, 0, 255))
    badge = render.clean(script.get("badge") or render.theme(script.get("category", ""))[1])
    bf = fonts.B(40)
    bw = bf.getlength(badge)
    d.rounded_rectangle([W / 2 - bw / 2 - 28, 160, W / 2 + bw / 2 + 28, 222], radius=31, fill=accent)
    d.text((W / 2 - bw / 2, 166), badge, font=bf, fill=WHITE)
    title = render.clean(script["title"])
    hls = [render.clean(h) for h in script.get("title_highlight", [])] or re.findall(r"[\d,.]+[%원만억조배]*", title)
    f, lines = wrap_fit(title, fonts.H, 980, 2, 112, 72)
    tl = text_layer([segments(ln, hls, WHITE, YEL) for ln in lines], f, line_gap=1.08)
    top = 245 if len(lines) == 2 else 290
    layer.paste(tl, (int((W - tl.width) / 2), top), tl)
    return layer


def watermark(base, fonts, channel):
    if not channel:
        return
    d = ImageDraw.Draw(base, "RGBA")
    f = fonts.B(36)
    tw = f.getlength(channel)
    x1 = W - 56
    d.rounded_rectangle([x1 - tw - 36, 62, x1, 120], radius=29, fill=(0, 0, 0, 150))
    d.text((x1 - tw - 18, 70), channel, font=f, fill=WHITE)


def progress(base, spans, now, color):
    d = ImageDraw.Draw(base)
    n = len(spans)
    gap = 8
    seg_w = (W - 40 - gap * (n - 1)) / n
    for i, (s, e) in enumerate(spans):
        x = 20 + i * (seg_w + gap)
        d.rectangle([x, 22, x + seg_w, 32], fill=(90, 90, 90))
        fill = clamp((now - s) / max(0.01, e - s))
        if fill > 0:
            d.rectangle([x, 22, x + seg_w * fill, 32], fill=color)


def parse_number(s: str):
    m = re.search(r"-?\d[\d,]*(\.\d+)?", s or "")
    if not m:
        return None
    raw = m.group(0)
    decimals = len(m.group(1)) - 1 if m.group(1) else 0
    return float(raw.replace(",", "")), decimals, "," in raw, s[:m.start()], s[m.end():]


def fmt_number(v, decimals, comma):
    s = f"{v:,.{decimals}f}" if comma else f"{v:.{decimals}f}"
    return s


def delta_color(delta: str):
    d = (delta or "").strip()
    if d.startswith(("▼", "-", "↓")) or "하락" in d or "감소" in d:
        return BLUE
    return RED


# ================================================================ 장면 준비
class Scene:
    def __init__(self, idx, n, sc, start, end, voice_start, chunks, image, fonts, script, accent):
        self.i, self.sc, self.start, self.end = idx, sc, start, end
        self.fonts, self.accent = fonts, accent
        self.highlights = [render.clean(h) for h in sc.get("highlight", [])]
        lay = sc.get("layout")
        if not lay:
            if idx == 0:
                lay = "hook"
            elif idx == n - 1:
                lay = "cta"
            elif image:
                lay = "image"
            elif sc.get("left") and sc.get("right"):
                lay = "vs"
            elif sc.get("number"):
                lay = "number"
            elif sc.get("index"):
                lay = "point"
            else:
                lay = "text"
        if lay == "image" and not image:
            lay = "text"
        self.layout = lay
        self.image = image
        self.boxed = lay in ("hook", "cta")
        # 자막 덩어리 시간
        self.chunks = []
        span = end - voice_start
        acc = voice_start
        for i, (txt, w) in enumerate(chunks):
            s = start if i == 0 else acc
            acc += span * w
            self.chunks.append((s, acc, txt))
        self._sub_cache = {}
        self._prepare(script)

    # 장면마다 바뀌지 않는 부품은 미리 그려 둔다
    def _prepare(self, script):
        f, sc, hl = self.fonts, self.sc, self.highlights
        caption = render.clean(sc.get("caption", ""))
        self.parts = {}
        if self.layout in ("hook", "cta"):
            lines_src = sc.get("lines") or None
            if lines_src:
                lines = [render.clean(x) for x in lines_src][:3]
                size = 240
                while size > 90 and max(f.H(size).getlength(x) for x in lines) > 900:
                    size -= 6
                fnt = f.H(size)
            else:
                fnt, lines = wrap_fit(caption or render.clean(script["title"]), f.H, 960, 3, 240, 110)
            self.parts["lines"] = []
            for j, ln in enumerate(lines):
                base = BLACK if j % 2 == 0 else RED
                lay = text_layer([segments(ln, hl, base, RED if base == BLACK else BLACK)], fnt, stroke=14,
                                 sf=WHITE, shadow=(12, 12, (150, 110, 0) if base == BLACK else (120, 0, 0)))
                self.parts["lines"].append(lay)
            if sc.get("sticker"):
                self.parts["sticker"] = sticker_layer(f, render.clean(sc["sticker"]), BLUE if self.layout == "hook" else RED)
            if self.layout == "cta":
                btn = Image.new("RGBA", (420, 130), (0, 0, 0, 0))
                bd = ImageDraw.Draw(btn)
                bd.rounded_rectangle([0, 0, 419, 129], radius=65, fill=RED)
                bf = f.H(64)
                label = render.clean(sc.get("button", "구독"))
                bd.text(((420 - bf.getlength(label)) / 2, 22), label, font=bf, fill=WHITE)
                self.parts["button"] = btn
        elif self.layout in ("text", "image"):
            if caption:
                if self.layout == "text":
                    fnt, lines = wrap_fit(caption, f.H, 960, 3, 170, 86)
                    self.parts["caption"] = text_layer([segments(ln, hl, WHITE, YEL) for ln in lines], fnt, stroke=8)
                else:
                    fnt, lines = wrap_fit(caption, f.H, 900, 2, 92, 60)
                    self.parts["caption"] = text_layer([segments(ln, hl, WHITE, YEL) for ln in lines], fnt, stroke=8)
            if self.layout == "image":
                im = Image.open(self.image)
                im = ImageOps.exif_transpose(im).convert("RGB")
                self.parts["img"] = ImageOps.fit(im, (1040, 700), Image.LANCZOS)
        elif self.layout == "point":
            idx = str(sc.get("index", ""))
            badge = Image.new("RGBA", (230, 230), (0, 0, 0, 0))
            bd = ImageDraw.Draw(badge)
            bd.ellipse([5, 5, 225, 225], fill=self.accent, outline=WHITE, width=8)
            bf = f.H(130)
            bd.text(((230 - bf.getlength(idx)) / 2, 30), idx, font=bf, fill=WHITE)
            self.parts["badge"] = badge
            if caption:
                fnt, lines = wrap_fit(caption, f.H, 960, 2, 140, 80)
                self.parts["caption"] = text_layer([segments(ln, hl, WHITE, YEL) for ln in lines], fnt, stroke=8)
        elif self.layout == "number":
            self.num = parse_number(str(sc.get("number", "")))
            self.unit = render.clean(sc.get("unit", ""))
            if sc.get("label"):
                self.parts["label"] = text_layer([[(render.clean(sc["label"]), (220, 220, 220))]], f.B(54))
            if sc.get("delta"):
                dl = render.clean(sc["delta"])
                tl = text_layer([[(dl, WHITE)]], f.H(80))
                box = Image.new("RGBA", (tl.width + 60, tl.height + 20), (0, 0, 0, 0))
                ImageDraw.Draw(box).rounded_rectangle([0, 0, box.width - 1, box.height - 1], radius=28,
                                                       fill=delta_color(dl))
                box.paste(tl, (30, 10), tl)
                self.parts["delta"] = box
        elif self.layout == "vs":
            for side in ("left", "right"):
                info = sc.get(side, {})
                up = str(info.get("arrow", "")).lower() in ("up", "▲", "+")
                down = str(info.get("arrow", "")).lower() in ("down", "▼", "-")
                col = RED if up else BLUE if down else (YEL if side == "left" else (0, 220, 255))
                arrow = "▲" if up else "▼" if down else ""
                panel = Image.new("RGBA", (470, 600), (0, 0, 0, 0))
                pd = ImageDraw.Draw(panel)
                bgc = tuple(int(c * 0.18) for c in col) + (235,)
                pd.rounded_rectangle([0, 0, 469, 599], radius=30, fill=bgc, outline=col, width=6)
                lab = text_layer([[(render.clean(str(info.get("label", ""))), WHITE)]],
                                 wrap_fit(render.clean(str(info.get("label", ""))), f.H, 420, 1, 60, 36)[0])
                panel.paste(lab, (int(235 - lab.width / 2), 40), lab)
                if arrow:
                    al = text_layer([[(arrow, col)]], f.H(130))
                    panel.paste(al, (int(235 - al.width / 2), 150), al)
                val = render.clean(str(info.get("value", "")))
                vf, vlines = wrap_fit(val, f.H, 430, 1, 150, 70)
                vl = text_layer([[(vlines[0] if vlines else "", col)]], vf)
                panel.paste(vl, (int(235 - vl.width / 2), 330), vl)
                unit = render.clean(str(info.get("unit", "")))
                if unit:
                    ul = text_layer([[(unit, WHITE)]], f.B(48))
                    panel.paste(ul, (int(235 - ul.width / 2), 500), ul)
                self.parts[side] = panel
            self.parts["vs"] = text_layer([[("VS", YEL)]], f.H(150), stroke=12)

    def subtitle(self, txt):
        if txt not in self._sub_cache:
            self._sub_cache[txt] = subtitle_layer(self.fonts, txt, self.highlights, boxed=self.boxed)
        return self._sub_cache[txt]

    def current_chunk(self, now):
        for s, e, txt in self.chunks:
            if now < e:
                return s, txt
        s, _, txt = self.chunks[-1]
        return s, txt


# ================================================================ 프레임 그리기
class Renderer:
    def __init__(self, script, scenes_raw, spans, voice_starts, chunk_lists, images, font_path, channel, sfx_kinds):
        self.fonts = Fonts(font_path)
        self.script = script
        self.accent = _rgb(render.theme(script.get("category", ""))[0])
        self.channel = channel
        self.spans = spans
        self.sfx = sfx_kinds
        n = len(scenes_raw)
        self.scenes = [Scene(i, n, sc, spans[i][0], spans[i][1], voice_starts[i], chunk_lists[i], images[i],
                             self.fonts, script, self.accent) for i, sc in enumerate(scenes_raw)]
        self.head = headline_layer(self.fonts, script, self.accent)
        self.src = render.clean(script.get("source_label", ""))
        self.rng = random.Random(3)

    def scene_at(self, now):
        for s in self.scenes:
            if now < s.end:
                return s
        return self.scenes[-1]

    def frame(self, now) -> Image.Image:
        s = self.scene_at(now)
        t = now - s.start
        dur = s.end - s.start
        f = self.fonts
        hook_like = s.layout in ("hook", "cta")
        if hook_like:
            base = burst(now)
        else:
            off = int((now * 50) % 80)
            base = body_bg(self.accent).crop((off, 0, off + W, H))
            base.paste(self.head, (0, 0), self.head)
        p = s.parts

        # ---- 장면별 중앙 요소
        if hook_like:
            lines = p["lines"]
            total_h = sum(l.height for l in lines) * 0.86
            y = (700 if s.layout == "hook" else 640) - total_h / 2
            for j, lay in enumerate(lines):
                sc_, al = pop(t, 0.0 + j * 0.12, 0.2, 0.3)
                breathe = 1 + 0.015 * math.sin(now * 3 + j)
                paste(base, lay, W / 2, y + lay.height * 0.43, sc_ * breathe, al, angle=(3 if j % 2 == 0 else -3))
                y += lay.height * 0.86
            if "sticker" in p:
                sc_, al = pop(t, 0.45, 0.25, 0.2)
                paste(base, p["sticker"], 860, 1110, sc_, al, angle=12 + 4 * math.sin(now * 4))
            if "button" in p:
                sc_, al = pop(t, 0.5, 0.25, 0.3)
                pulse = 1 + 0.06 * max(0, math.sin((t - 0.8) * 5)) if t > 0.8 else 1
                paste(base, p["button"], W / 2, 1120, sc_ * pulse, al)
        elif s.layout == "text":
            if "caption" in p:
                sc_, al = pop(t, 0.03, 0.22, 0.5)
                paste(base, p["caption"], W / 2, CENTER_Y, sc_ * (1 + 0.04 * t / max(1, dur)), al)
        elif s.layout == "image":
            img = p["img"]
            z = 1 + 0.06 * clamp(t / max(1, dur))
            sc_, al = pop(t, 0.0, 0.25, 0.85)
            im = img.resize((int(img.width * z * sc_), int(img.height * z * sc_)), Image.BILINEAR)
            cw, ch = 1000, 640
            l, tp = (im.width - cw) // 2, (im.height - ch) // 2
            im = im.crop((max(0, l), max(0, tp), max(0, l) + min(cw, im.width), max(0, tp) + min(ch, im.height)))
            mask = Image.new("L", im.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=34, fill=255)
            base.paste(im, (int(W / 2 - im.width / 2), int(CENTER_Y - 40 - im.height / 2)), mask)
            if "caption" in p:
                sc2, al2 = pop(t, 0.25, 0.2, 0.6)
                paste(base, p["caption"], W / 2, CENTER_Y + 250, sc2, al2)
            credit = render.clean(s.sc.get("image_credit", ""))
            if credit:
                ImageDraw.Draw(base).text((W / 2 + 480 - f.B(26).getlength(credit), CENTER_Y - 350), credit,
                                          font=f.B(26), fill=(230, 230, 230))
        elif s.layout == "point":
            sc_, al = pop(t, 0.0, 0.22, 0.2)
            paste(base, p["badge"], W / 2, 700, sc_, al, angle=-8 * (1 - clamp(t / 0.25)))
            if "caption" in p:
                sc2, al2 = pop(t, 0.18, 0.22, 0.5)
                paste(base, p["caption"], W / 2, 1000, sc2, al2)
        elif s.layout == "number":
            if "label" in p:
                paste(base, p["label"], W / 2, 640, 1, clamp(t / 0.2))
            if s.num:
                v, dec, comma, pre, post = s.num
                x = ease_out(clamp((t - 0.05) / 0.9))
                # 환율처럼 큰 수는 0이 아니라 근처(90%)에서 출발해야 어색한 중간값이 안 보인다
                v0 = v * 0.9 if abs(v) >= 100 else 0.0
                txt = pre + fmt_number(v0 + (v - v0) * x, dec, comma) + post
                # 최종 값 기준으로 크기를 정해 카운트업 중에 크기가 흔들리지 않게 한다
                if not hasattr(s, "_nf"):
                    final_txt = pre + fmt_number(v, dec, comma) + post + s.unit
                    size = 230
                    while size > 90 and f.H(size).getlength(final_txt) > 960:
                        size -= 8
                    s._nf = f.H(size)
                nf = s._nf
                lay = text_layer([[(txt, WHITE)] + ([(s.unit, YEL)] if s.unit else [])], nf, stroke=6,
                                 sf=tuple(int(c * 0.3) for c in self.accent))
                sc_, al = pop(t, 0.0, 0.2, 0.7)
                paste(base, lay, W / 2, 880, sc_, al)
            if "delta" in p:
                sc_, al = pop(t, 0.85, 0.22, 0.3)
                paste(base, p["delta"], W / 2, 1110, sc_, al)
        elif s.layout == "vs":
            for side, x0, delay in (("left", 290, 0.0), ("right", 790, 0.12)):
                k = ease_out(clamp((t - delay) / 0.3))
                dx = (1 - k) * (-700 if side == "left" else 700)
                paste(base, p[side], x0 + dx, 880, 1, clamp(k * 2))
            if t >= 0.38:
                k = clamp((t - 0.38) / 0.18)
                paste(base, p["vs"], W / 2, 860, 2.6 - 1.6 * ease_out(k), clamp(k * 3))

        # ---- 자막
        cs, txt = s.current_chunk(now)
        sub = s.subtitle(txt)
        sc_, _ = pop(now, cs, 0.14, 0.82)
        paste(base, sub, W / 2, 1350 if s.boxed else SUB_Y + sub.height / 2 - 40, sc_)

        # ---- 출처 / 진행바 / 워터마크
        if not hook_like and self.src:
            d = ImageDraw.Draw(base, "RGBA")
            sf = f.B(30)
            text = f"출처: {self.src}"
            d.text(((W - sf.getlength(text)) / 2, 1535), text, font=sf, fill=(255, 255, 255, 150))
        progress(base, self.spans, now, YEL if not hook_like else BLACK)
        watermark(base, f, self.channel)

        # ---- 전환 번쩍임 + 흔들림
        if s.i > 0 and t < 0.12:
            flash = Image.new("RGB", (W, H), WHITE)
            base = Image.blend(base, flash, 0.55 * (1 - t / 0.12))
        amp = 0
        if s.layout == "hook" and t < 0.3:
            amp = 14 * (1 - t / 0.3)
        if s.layout == "vs" and 0.5 < t < 0.85:
            amp = 18 * (1 - (t - 0.5) / 0.35)
        if self.sfx[s.i] == "boom" and t < 0.35:
            amp = max(amp, 16 * (1 - t / 0.35))
        if amp > 0.5:
            dx, dy = self.rng.uniform(-amp, amp), self.rng.uniform(-amp, amp)
            shaken = Image.new("RGB", (W, H), BLACK)
            shaken.paste(base.resize((W + 40, H + 70)), (int(-20 + dx), int(-35 + dy)))
            base = shaken
        return base

    def cover(self) -> Image.Image:
        """썸네일: 첫 장면이 다 등장한 순간."""
        return self.frame(min(self.scenes[0].end - 0.05, self.scenes[0].start + 0.9))


def encode(renderer: Renderer, total: float, wav: Path, out: Path, ffmpeg: str, log=print) -> None:
    n = int(math.ceil(total * FPS))
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "medium",
           "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        step = max(1, n // 10)
        for k in range(n):
            p.stdin.write(renderer.frame(k / FPS).tobytes())
            if k % step == 0:
                log(f"  영상 그리는 중… {int(100 * k / n)}%")
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        raise RuntimeError(f"영상 인코딩 실패\n{err[-1500:]}")
