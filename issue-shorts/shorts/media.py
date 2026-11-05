"""ffmpeg 호출과 오디오 처리(디코딩·믹싱)."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100


def run(cmd: list[str], what: str) -> None:
    p = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        tail = p.stderr.decode("utf-8", "replace")[-1500:]
        raise RuntimeError(f"{what} 실패 (ffmpeg 종료코드 {p.returncode})\n{tail}")


def decode(ffmpeg: str, path: Path | str) -> np.ndarray:
    """아무 오디오 파일 → float32 mono 44.1kHz 배열."""
    p = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True, stdin=subprocess.DEVNULL,
    )
    if p.returncode != 0:
        raise RuntimeError(f"오디오 읽기 실패: {path}\n{p.stderr.decode('utf-8', 'replace')[-800:]}")
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def trim_silence(x: np.ndarray, thresh: float = 0.01, pad: float = 0.05) -> np.ndarray:
    """TTS 앞뒤 무음 제거 (말 사이 템포를 빠르게)."""
    idx = np.where(np.abs(x) > thresh)[0]
    if len(idx) == 0:
        return x
    p = int(pad * SR)
    return x[max(0, idx[0] - p): min(len(x), idx[-1] + p)]


def write_wav(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1.0, 1.0)
    pcm = (x * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def place(track: np.ndarray, clip: np.ndarray, at_sec: float, gain: float) -> None:
    start = int(at_sec * SR)
    if start >= len(track):
        return
    end = min(len(track), start + len(clip))
    track[start:end] += clip[: end - start] * gain


def loop_to(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) == 0:
        return np.zeros(n, dtype=np.float32)
    reps = int(np.ceil(n / len(x)))
    return np.tile(x, reps)[:n]


def normalize(x: np.ndarray, peak: float = 0.95) -> np.ndarray:
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    return x if m < 1e-6 else x * (peak / m)
