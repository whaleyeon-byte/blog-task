"""폰트(Pretendard, SIL OFL 무료 상업 사용 가능) 다운로드. 실패해도 윈도우 '맑은 고딕'으로 동작."""
from __future__ import annotations

import io
import sys
import zipfile

from .config import ASSETS

URL = "https://github.com/orioncactus/pretendard/releases/download/v1.3.9/Pretendard-1.3.9.zip"
WANT = ["Pretendard-ExtraBold.otf", "Pretendard-Bold.otf", "Pretendard-Black.otf"]


def main() -> int:
    dest = ASSETS / "fonts"
    dest.mkdir(parents=True, exist_ok=True)
    if all((dest / w).exists() for w in WANT):
        print("폰트: 이미 있음")
        return 0
    try:
        import requests
        print("폰트 다운로드 중 (Pretendard, 약 45MB)…")
        r = requests.get(URL, timeout=120)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for w in WANT:
                (dest / w).write_bytes(z.read(f"public/static/{w}"))
        (dest / "LICENSE-Pretendard.txt").write_text(
            "Pretendard — SIL Open Font License 1.1 — https://github.com/orioncactus/pretendard\n",
            encoding="utf-8")
        print("폰트: 설치 완료")
        return 0
    except Exception as e:
        print(f"[경고] 폰트 다운로드 실패({e}). 윈도우 기본 '맑은 고딕'을 사용합니다.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
