"""효과음. freesound.org(CC0 만) → 캐시 → 실패 시 직접 합성한 효과음."""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np

from .config import ASSETS
from .media import SR, write_wav

SFX_DIR = ASSETS / "sfx"

QUERIES = {
    "whoosh": ("whoosh transition", "0.2 TO 1.5"),
    "pop": ("pop click ui", "0.05 TO 0.8"),
    "ding": ("notification ding", "0.2 TO 2"),
    "boom": ("cinematic boom hit", "0.5 TO 3"),
    "alert": ("news alert sting", "0.3 TO 3"),
}
KINDS = set(QUERIES) | {"none"}
CACHE_TARGET = 4  # 종류별로 이 정도 모이면 더 받지 않음
_disabled = False  # 한 번 실패하면 이번 실행에서는 다시 시도하지 않음


def get_sfx(kind: str, cfg: dict, log=print) -> Path | None:
    global _disabled
    if not kind or kind == "none":
        return None
    if kind not in QUERIES:
        log(f"  [경고] 모르는 효과음 '{kind}' → whoosh 로 대체")
        kind = "whoosh"
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    cached = sorted(SFX_DIR.glob(f"{kind}_fs*.mp3"))
    key = (cfg.get("freesound_api_key") or "").strip()
    if key and not _disabled and len(cached) < CACHE_TARGET:
        try:
            cached += _fetch_freesound(kind, key, CACHE_TARGET - len(cached), log)
        except Exception as e:
            _disabled = True
            # 오류 문구에 URL(API 키 포함)이 섞이지 않도록 종류만 출력
            reason = str(e) if isinstance(e, RuntimeError) else e.__class__.__name__
            log(f"  [경고] freesound 연결 실패({reason}) → 이번엔 내장/저장된 효과음 사용")
    if cached:
        return random.choice(cached)
    return _synth(kind)


def _fetch_freesound(kind: str, key: str, n: int, log) -> list[Path]:
    import requests

    query, dur = QUERIES[kind]
    r = requests.get(
        "https://freesound.org/apiv2/search/text/",
        params={
            "query": query,
            "filter": f'duration:[{dur}] license:"Creative Commons 0"',
            "fields": "id,name,previews,duration",
            "sort": "rating_desc",
            "page_size": 15,
            "token": key,
        },
        timeout=15,
    )
    if r.status_code == 401:
        raise RuntimeError("API 키가 올바르지 않습니다 (401)")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    results = r.json().get("results", [])
    random.shuffle(results)
    got = []
    for item in results[:n]:
        url = item.get("previews", {}).get("preview-hq-mp3")
        if not url:
            continue
        dest = SFX_DIR / f"{kind}_fs{item['id']}.mp3"
        if not dest.exists():
            a = requests.get(url, timeout=20)
            a.raise_for_status()
            dest.write_bytes(a.content)
        got.append(dest)
    if got:
        log(f"  freesound 효과음 {len(got)}개 저장 ({kind}, CC0)")
    return got


def _synth(kind: str) -> Path:
    dest = SFX_DIR / f"{kind}_builtin.wav"
    if dest.exists():
        return dest
    rng = np.random.default_rng(7)
    if kind == "whoosh":
        n = int(0.55 * SR)
        noise = rng.standard_normal(n).astype(np.float32)
        # 1차 저역통과 필터의 계수를 시간에 따라 바꿔 '쉭' 하는 스윕을 만든다
        a = np.linspace(0.02, 0.35, n) ** 1.5
        y = np.zeros(n, dtype=np.float32)
        acc = 0.0
        for i in range(n):
            acc += a[i] * (noise[i] - acc)
            y[i] = acc
        env = np.sin(np.linspace(0, np.pi, n)) ** 2
        x = y * env
    elif kind == "pop":
        t = np.arange(int(0.12 * SR)) / SR
        f = 900 * np.exp(-t * 30) + 300
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35)
    elif kind in ("ding", "alert"):
        t = np.arange(int(0.9 * SR)) / SR
        base = 1318.5 if kind == "ding" else 880.0
        x = (np.sin(2 * np.pi * base * t) + 0.4 * np.sin(2 * np.pi * base * 2.01 * t)) * np.exp(-t * 5)
        if kind == "alert":
            t2 = t[: int(0.45 * SR)]
            x2 = np.sin(2 * np.pi * 1174.7 * t2) * np.exp(-t2 * 6)
            x[int(0.15 * SR): int(0.15 * SR) + len(x2)] += x2
    else:  # boom
        t = np.arange(int(1.2 * SR)) / SR
        f = 110 * np.exp(-t * 3) + 38
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.5)
        x += 0.3 * rng.standard_normal(len(t)) * np.exp(-t * 25)
    x = x.astype(np.float32)
    x /= max(1e-6, float(np.max(np.abs(x))))
    write_wav(dest, x * 0.9)
    return dest
