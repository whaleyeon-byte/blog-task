"""목소리 비교: 3개 목소리 × 4단계 차분함 = 12개 샘플을 만들고, 고른 번호를 config.json 에 저장."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np

from . import media, tts
from .config import CONFIG_PATH, OUTPUT, load_config

VOICES = [
    ("ko-KR-InJoonNeural", "인준"),
    ("ko-KR-HyunsuMultilingualNeural", "현수"),
    ("ko-KR-SunHiNeural", "선희"),
]
PRESETS = [
    # 이름, 빠르기, 음높이, 장면 사이 쉼(초)
    ("기본", "+12%", "+0Hz", 0.15),
    ("중간", "+6%", "-2Hz", 0.22),
    ("차분", "+0%", "-3Hz", 0.30),
    ("아주차분", "-8%", "-6Hz", 0.45),
]
SAMPLE = [
    "원 달러 환율이 사흘 연속 1340원대에 머물고 있습니다.",
    "연말에는 오를까요, 내릴까요? 전문가 전망은 엇갈립니다.",
]


def options():
    n = 0
    for v, vname in VOICES:
        for pname, rate, pitch, gap in PRESETS:
            n += 1
            yield n, v, vname, pname, rate, pitch, gap


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    cfg = load_config()
    out = OUTPUT / "voice_test"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.wav"):  # 이전 번호 체계의 샘플과 헷갈리지 않도록 정리
        old.unlink(missing_ok=True)
    print(f"목소리 샘플 {len(VOICES) * len(PRESETS)}개를 만드는 중… (30초~1분)")
    made = 0
    for n, v, vname, pname, rate, pitch, gap in options():
        c = dict(cfg, voice=v, voice_rate=rate, voice_pitch=pitch)
        try:
            parts = []
            for i, line in enumerate(SAMPLE):
                p = tts.synthesize(line, out / f"_tmp{n}_{i}", c)
                parts.append(media.trim_silence(media.decode(cfg["ffmpeg_path"], p)))
                p.unlink(missing_ok=True)
            # 두 문장 사이에 실제 영상과 같은 '장면 사이 쉼'을 넣는다
            x = np.concatenate([parts[0], np.zeros(int(gap * media.SR), np.float32), parts[1]])
            media.write_wav(out / f"{n}_{vname}_{pname}.wav", media.normalize(x, 0.9))
            made += 1
            print(f"  {n}. {vname} · {pname}  (빠르기 {rate}, 음높이 {pitch}, 쉼 {gap}초)")
        except Exception as e:
            print(f"  {n}. {vname} · {pname}  → 실패: {e}")
    if made == 0:
        print("[오류] 샘플을 하나도 못 만들었습니다. 인터넷 연결을 확인해 주세요.")
        return 1
    if os.name == "nt":
        os.startfile(str(out))  # 탐색기로 폴더 열기
    print(f"\n폴더: {out}")
    print("파일을 하나씩 들어보고 마음에 드는 번호를 입력하세요.")
    try:
        choice = input("번호 (Enter = 저장하지 않고 종료): ").strip()
    except EOFError:
        choice = ""
    pick = {o[0]: o for o in options()}.get(int(choice)) if choice.isdigit() else None
    if not pick:
        print("저장하지 않았습니다.")
        return 0
    _, v, vname, pname, rate, pitch, gap = pick
    raw = {}
    if CONFIG_PATH.exists():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    raw.update(voice=v, voice_rate=rate, voice_pitch=pitch, scene_gap=gap)
    CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {vname} · {pname}. 다음 쇼츠부터 이 목소리로 만들어집니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
