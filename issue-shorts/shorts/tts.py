"""음성 합성. 엔진을 바꿔 끼울 수 있게 분리 (2단계: 내 목소리 복제 엔진 추가 예정)."""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

import numpy as np

from .media import SR, write_wav


def synthesize(text: str, out_path: Path, cfg: dict) -> Path:
    engine = cfg.get("tts_engine", "edge")
    if engine == "edge":
        return _edge(text, out_path.with_suffix(".mp3"), cfg)
    if engine == "dummy":
        return _dummy(text, out_path.with_suffix(".wav"))
    raise ValueError(f"알 수 없는 tts_engine: {engine} (edge 또는 dummy)")


def _edge(text: str, out: Path, cfg: dict) -> Path:
    import edge_tts  # 지연 import: dummy 테스트 시 불필요

    last_err = None
    for attempt in range(1, 4):
        try:
            comm = edge_tts.Communicate(text, cfg["voice"], rate=cfg.get("voice_rate", "+0%"),
                                         pitch=cfg.get("voice_pitch", "+0Hz"))
            asyncio.run(comm.save(str(out)))
            if out.exists() and out.stat().st_size > 1000:
                return out
            last_err = RuntimeError("빈 음성 파일이 생성됨")
        except Exception as e:  # 네트워크 오류 등
            last_err = e
        time.sleep(2 * attempt)
    raise RuntimeError(
        f"음성 생성 3회 실패: {last_err}\n"
        "  - 인터넷 연결을 확인해 주세요.\n"
        "  - config.json 의 voice 이름이 맞는지 확인해 주세요 (예: ko-KR-InJoonNeural)."
    )


def _dummy(text: str, out: Path) -> Path:
    """네트워크 없이 파이프라인을 시험하는 용도. 글자수 기반 길이의 낮은 험(hum)."""
    syllables = len(re.sub(r"\s", "", text))
    dur = max(0.8, syllables / 7.0)
    t = np.arange(int(dur * SR)) / SR
    x = 0.05 * np.sin(2 * np.pi * 180 * t).astype(np.float32)
    write_wav(out, x)
    return out
