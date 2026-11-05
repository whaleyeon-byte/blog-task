"""설정 로드. config.json 이 없거나 일부 값이 비어 있어도 기본값으로 동작한다."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "output"

DEFAULTS = {
    "channel_name": "",
    "freesound_api_key": "",
    "tts_engine": "edge",               # edge | dummy(테스트용 무음)
    "voice": "ko-KR-InJoonNeural",      # 남성. 여성: ko-KR-SunHiNeural
    "voice_rate": "+12%",
    "ffmpeg_path": "",
    "ffprobe_path": "",
    "font_path": "",
    "bgm_volume": 0.08,                 # assets/bgm 에 mp3 를 넣었을 때만 사용
    "sfx_volume": 0.55,
}

FONT_CANDIDATES = [
    ASSETS / "fonts" / "Pretendard-ExtraBold.otf",
    ASSETS / "fonts" / "Pretendard-Bold.otf",
    Path("C:/Windows/Fonts/malgunbd.ttf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
]


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                user = json.load(f)
            cfg.update({k: v for k, v in user.items() if v not in (None,)})
        except json.JSONDecodeError as e:
            sys.exit(f"[오류] config.json 형식이 잘못됐습니다: {e}\n"
                     f"       setup_windows.bat 을 다시 실행하거나 파일을 고쳐 주세요.")
    # 환경변수로 덮어쓰기(테스트용)
    if os.environ.get("SHORTS_TTS_ENGINE"):
        cfg["tts_engine"] = os.environ["SHORTS_TTS_ENGINE"]
    cfg["ffmpeg_path"] = _find_tool("ffmpeg", cfg.get("ffmpeg_path"))
    cfg["ffprobe_path"] = _find_tool("ffprobe", cfg.get("ffprobe_path"),
                                     sibling_of=cfg["ffmpeg_path"])
    cfg["font_path"] = _find_font(cfg.get("font_path"))
    return cfg


def _find_tool(name: str, configured: str | None, sibling_of: str | None = None) -> str:
    if configured and Path(configured).exists():
        return str(configured)
    if sibling_of:
        exe = ".exe" if sibling_of.lower().endswith(".exe") else ""
        cand = Path(sibling_of).with_name(name + exe)
        if cand.exists():
            return str(cand)
    found = shutil.which(name)
    if found:
        return found
    # winget 으로 설치했지만 PATH 가 아직 갱신 안 된 경우
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for p in Path(local, "Microsoft", "WinGet", "Packages").glob(f"Gyan.FFmpeg*/**/bin/{name}.exe"):
            return str(p)
    sys.exit(f"[오류] {name} 을(를) 찾지 못했습니다. setup_windows.bat 을 먼저 실행해 주세요.")


def _find_font(configured: str | None) -> str:
    if configured and Path(configured).exists():
        return str(configured)
    for p in FONT_CANDIDATES:
        if p.exists():
            return str(p)
    sys.exit("[오류] 한글 폰트를 찾지 못했습니다. `python -m shorts.setup_assets` 를 실행해 주세요.")
