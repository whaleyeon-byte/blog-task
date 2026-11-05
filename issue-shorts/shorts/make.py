"""대본(JSON) → 세로 쇼츠 mp4.

사용법:
    python make_short.py scripts/2026-11-05_금리.json
    python make_short.py scripts/example.json --engine dummy   # 네트워크 없이 시험
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import media, motion, render, sfx, tts
from .config import ASSETS, OUTPUT, ROOT, load_config

TAIL = 0.6        # 마지막 여운(초)
SUB_MAX = 16      # 자막 한 덩어리 최대 글자수(공백 포함)
TARGET_MAX = 59.0
LAYOUTS = {"hook", "text", "point", "number", "vs", "image", "cta"}


# ---------------------------------------------------------------- 검증
def load_script(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"[오류] 대본 파일이 없습니다: {path}")
    try:
        s = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"[오류] 대본 JSON 형식 오류: {e}")
    errs = []
    if not str(s.get("title", "")).strip():
        errs.append("title(화면 상단 제목)이 비어 있음")
    scenes = s.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errs.append("scenes 가 비어 있음")
        scenes = []
    for i, sc in enumerate(scenes, 1):
        if not isinstance(sc, dict) or not str(sc.get("text", "")).strip():
            errs.append(f"scenes[{i}] 의 text(내레이션)가 비어 있음")
            continue
        if sc.get("sfx") and sc["sfx"] not in sfx.KINDS:
            errs.append(f"scenes[{i}].sfx '{sc['sfx']}' 는 {sorted(sfx.KINDS)} 중 하나여야 함")
        if not isinstance(sc.get("highlight", []), list):
            errs.append(f"scenes[{i}].highlight 는 배열이어야 함")
        lay = sc.get("layout")
        if lay and lay not in LAYOUTS:
            errs.append(f"scenes[{i}].layout '{lay}' 는 {sorted(LAYOUTS)} 중 하나여야 함")
        if lay == "vs" and not (isinstance(sc.get("left"), dict) and isinstance(sc.get("right"), dict)):
            errs.append(f"scenes[{i}] layout 'vs' 에는 left/right 객체가 필요함")
        if lay == "number" and not motion.parse_number(str(sc.get("number", ""))):
            errs.append(f"scenes[{i}] layout 'number' 에는 숫자가 들어간 number 값이 필요함")
    if errs:
        sys.exit("[오류] 대본 검증 실패:\n  - " + "\n  - ".join(errs))
    return s


# ---------------------------------------------------------------- 자막 분할
def chunk_subtitles(text: str, max_len: int = SUB_MAX) -> list[str]:
    words = render.clean(text).split()
    chunks, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and len(trial) > max_len:
            chunks.append(cur)
            cur = w
        else:
            cur = trial
        if re.search(r"[.!?…]$", cur) and len(cur) >= max_len * 0.5:
            chunks.append(cur)
            cur = ""
    if cur:
        chunks.append(cur)
    # 너무 짧은 꼬리는 앞 덩어리에 붙인다
    if len(chunks) >= 2 and len(chunks[-1]) <= 3:
        chunks[-2] = f"{chunks[-2]} {chunks.pop()}"
    return chunks


def _weights(chunks: list[str]) -> list[float]:
    w = [max(2, len(re.sub(r"\s", "", c))) + 1.5 * len(re.findall(r"[,.!?…]", c)) for c in chunks]
    s = sum(w)
    return [x / s for x in w]


def _resolve_image(value: str, script_dir: Path, work: Path, log) -> str | None:
    if not value:
        return None
    if re.match(r"https?://", value):
        try:
            import requests
            r = requests.get(value, timeout=20, headers={"User-Agent": "issue-shorts/1.0"})
            r.raise_for_status()
            dest = work / f"img_{abs(hash(value)) % 10**8}.img"
            dest.write_bytes(r.content)
            return str(dest)
        except Exception as e:
            log(f"  [경고] 이미지 다운로드 실패 → 텍스트 카드로 대체: {value} ({e})")
            return None
    for base in (script_dir, ROOT, ASSETS / "images"):
        p = (base / value)
        if p.exists():
            return str(p)
    log(f"  [경고] 이미지 파일 없음 → 텍스트 카드로 대체: {value}")
    return None


def _slug(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "_", text).strip("_")
    return s[:24] or "short"


# ---------------------------------------------------------------- 메인
def build(script_path: Path, engine: str | None = None, keep_work: bool = False, log=print) -> Path:
    t0 = time.time()
    cfg = load_config()
    if engine:
        cfg["tts_engine"] = engine
    script = load_script(script_path)
    ffmpeg = cfg["ffmpeg_path"]
    scenes = script["scenes"]
    GAP = float(cfg.get("scene_gap", 0.15))  # 장면 사이 쉼(초)

    out_dir = OUTPUT / f"{datetime.now():%Y%m%d_%H%M%S}_{_slug(script.get('slug') or script['title'])}"
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    log(f"▶ 출력 폴더: {out_dir}")
    log(f"▶ 음성 엔진: {cfg['tts_engine']} / 목소리: {cfg['voice']}")

    # 1) 음성
    voices = []
    for i, sc in enumerate(scenes, 1):
        log(f"  음성 {i}/{len(scenes)}: {sc['text'][:30]}…")
        p = tts.synthesize(render.clean(sc["text"]), work / f"v{i:02d}", cfg)
        a = media.trim_silence(media.decode(ffmpeg, p))
        voices.append(a)

    # 2) 타임라인
    timeline, t = [], 0.1
    for i, (sc, a) in enumerate(zip(scenes, voices)):
        dur = len(a) / media.SR
        timeline.append((t, dur))
        t += dur + GAP
    total = t - GAP + TAIL
    if total > TARGET_MAX:
        log(f"  [경고] 총 길이 {total:.1f}초 — 60초를 넘습니다. 대본을 줄이는 걸 권장합니다.")

    # 3) 오디오 믹스
    n = int(total * media.SR) + media.SR
    voice_track = np.zeros(n, dtype=np.float32)
    fx_track = np.zeros(n, dtype=np.float32)
    kinds = [sc.get("sfx") or ("alert" if i == 0 else "ding" if i == len(scenes) - 1 else "whoosh")
             for i, sc in enumerate(scenes)]
    for i, ((start, _), a, kind) in enumerate(zip(timeline, voices, kinds)):
        media.place(voice_track, a, start, 1.0)
        fx = sfx.get_sfx(kind, cfg, log)
        if fx is not None:
            clip = media.normalize(media.decode(ffmpeg, fx)[: int(2.5 * media.SR)], 1.0)
            fade = np.linspace(1, 0, min(len(clip), int(0.3 * media.SR)))
            clip[-len(fade):] *= fade
            media.place(fx_track, clip, max(0.0, start - 0.12), float(cfg["sfx_volume"]))
    mix = media.normalize(voice_track) + fx_track
    bgms = sorted((ASSETS / "bgm").glob("*.mp3")) + sorted((ASSETS / "bgm").glob("*.wav"))
    if bgms:
        pick = random.choice(bgms)
        log(f"  배경음악: {pick.name}")
        b = media.loop_to(media.normalize(media.decode(ffmpeg, pick)), n)
        b[-int(1.5 * media.SR):] *= np.linspace(1, 0, int(1.5 * media.SR))
        mix += b * float(cfg["bgm_volume"])
    mix = media.normalize(mix[: int(total * media.SR)], 0.92)
    wav = work / "mix.wav"
    media.write_wav(wav, mix)

    # 4~5) 영상
    script_dir = script_path.resolve().parent
    channel = render.clean(cfg.get("channel_name", ""))
    images = [_resolve_image(sc.get("image", ""), script_dir, work, log) for sc in scenes]
    final = out_dir / "short.mp4"
    style = script.get("style") or cfg.get("style", "motion")
    if style == "motion":
        starts = [0.0] + [timeline[i][0] for i in range(1, len(scenes))]
        spans = [(starts[i], starts[i + 1] if i + 1 < len(scenes) else total) for i in range(len(scenes))]
        chunk_lists = []
        for sc in scenes:
            ch = chunk_subtitles(sc["text"])
            chunk_lists.append(list(zip(ch, _weights(ch))))
        rd = motion.Renderer(script, scenes, spans, [t_[0] for t_ in timeline], chunk_lists, images,
                             cfg["font_path"], channel, kinds)
        rd.cover().save(out_dir / "cover.png")
        motion.encode(rd, total, wav, final, ffmpeg, log)
    else:
        _render_cards(script, scenes, timeline, images, total, GAP, channel, cfg, work, wav, final, out_dir, log)

    # 6) 업로드 정보
    write_upload_info(out_dir / "upload.txt", script, total)
    shutil.copy(script_path, out_dir / "script.json")
    if not keep_work:
        shutil.rmtree(work, ignore_errors=True)

    log(f"✔ 완성: {final}  ({total:.1f}초, {time.time() - t0:.0f}초 소요)")
    return final


def _render_cards(script, scenes, timeline, images, total, GAP, channel, cfg, work, wav, final, out_dir, log):
    """예전 방식(style: card) — 정지 카드 + 자막."""
    ffmpeg = cfg["ffmpeg_path"]
    entries = []
    k = 0
    for i, (sc, (start, dur)) in enumerate(zip(scenes, timeline)):
        image = images[i]
        chunks = chunk_subtitles(sc["text"])
        # 장면 시작 ~ 다음 장면 시작까지를 덩어리 비율로 나눈다
        span = dur + (GAP if i < len(scenes) - 1 else TAIL)
        if i == 0:
            span += start  # 맨 앞 0.1초 포함
        for chunk, w in zip(chunks, _weights(chunks)):
            k += 1
            f = work / f"f{k:04d}.png"
            elapsed = sum(e[1] for e in entries)
            render.render_frame(f, font_path=cfg["font_path"], script=script, scene=sc,
                                sub_lines_text=chunk, progress=elapsed / total,
                                channel=channel, image_path=image)
            entries.append((f.name, span * w))
    log(f"  프레임 {k}장 생성")

    lst = work / "frames.txt"
    with open(lst, "w", encoding="utf-8") as fh:
        for name, d in entries:
            fh.write(f"file '{name}'\nduration {d:.3f}\n")
        fh.write(f"file '{entries[-1][0]}'\n")  # concat demuxer 마지막 프레임 규칙

    media.run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
               "-i", str(wav), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264",
               "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", "-t", f"{total:.3f}", str(final)], "영상 인코딩")
    # 썸네일용 첫 화면
    shutil.copy(work / "f0001.png", out_dir / "cover.png")


def write_upload_info(path: Path, s: dict, total: float) -> None:
    tags = s.get("hashtags") or []
    tags = [t if t.startswith("#") else f"#{t}" for t in tags]
    if "#shorts" not in [t.lower() for t in tags]:
        tags.append("#shorts")
    sources = s.get("sources") or []
    lines = [
        "■ 제목", s.get("youtube_title") or s["title"], "",
        "■ 설명", s.get("description", "").strip(), "",
        "■ 출처", *[f"- {x}" for x in sources], "",
        "■ 해시태그", " ".join(tags), "",
        f"■ 길이: {total:.1f}초",
        "",
        "■ 업로드 전 체크",
        "- [ ] 수치·날짜·인명을 출처 기사와 한 번 더 대조했다",
        "- [ ] 특정 개인을 단정·비방하는 표현이 없다",
        "- [ ] 투자·의료 내용은 '정보 제공'이며 권유가 아니다",
        "- [ ] 사용한 이미지는 내가 만들었거나 사용 허락된 것이다",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="대본 JSON → 쇼츠 mp4")
    ap.add_argument("script", type=Path)
    ap.add_argument("--engine", choices=["edge", "dummy"], help="음성 엔진 강제 지정")
    ap.add_argument("--keep-work", action="store_true", help="중간 파일 보존(디버그)")
    a = ap.parse_args(argv)
    try:
        build(a.script, a.engine, a.keep_work)
    except RuntimeError as e:
        sys.exit(f"[오류] {e}")
    except KeyboardInterrupt:
        sys.exit("중단됨")
