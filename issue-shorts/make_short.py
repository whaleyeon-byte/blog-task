"""대본 JSON → 쇼츠 mp4.  예) python make_short.py scripts/example.json"""
import sys

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")  # 윈도우 콘솔 한글 깨짐 방지
    except Exception:
        pass

from shorts.make import main

if __name__ == "__main__":
    main()
