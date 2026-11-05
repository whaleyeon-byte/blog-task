# 이슈 쇼츠 메이커 (Windows)

Claude Code 에서 **"이슈 쇼츠 만들어줘"** 한마디로
이슈 검색 → 사실 확인 → 대본 → AI 음성 → 자막·효과음·워터마크 → **세로 쇼츠 mp4(1080×1920)** 까지 만듭니다.

## 1. 처음 한 번: 설치 (약 5~10분)
1. 이 저장소를 받습니다. GitHub 에서 **Code → Download ZIP** → 압축 풀기 (또는 `git clone`)
   - 경로에 한글/공백이 없는 곳이 가장 안전합니다. 예: `C:\shorts\issue-shorts`
2. `issue-shorts` 폴더의 **`setup_windows.bat` 더블클릭**
   - 파이썬·FFmpeg 가 없으면 자동 설치(winget) → 프로그램·폰트 설치
   - 효과음 키(선택): freesound.org 무료 가입 → https://freesound.org/apiv2/apply 에서 키 발급 → 붙여넣기
   - 채널 이름(워터마크), 목소리(남/여) 선택
   - 마지막에 **샘플 영상**을 만들어 폴더를 열어 줍니다. 소리가 나오면 설치 성공.
3. "Windows의 PC 보호" 창이 뜨면 **추가 정보 → 실행**.

## 2. 매번: 만들기
1. Claude Code(데스크톱 앱의 Code 탭 또는 터미널 `claude`)에서 **`issue-shorts` 폴더**를 엽니다.
2. 입력: **`이슈 쇼츠 만들어줘`**
   - 주제 지정도 가능: `금리 인하 주제로 쇼츠 만들어줘`, `오늘 IT 이슈로 하나`
3. 결과: `output\날짜_제목\`
   - `short.mp4` 영상 · `cover.png` 첫 화면 · `upload.txt` 제목/설명/해시태그/출처/체크리스트

## 설정 바꾸기
`setup_windows.bat` 을 다시 실행하면 됩니다(Enter = 기존 값 유지). 또는 `config.json` 직접 수정:

| 항목 | 설명 |
|---|---|
| `channel_name` | 오른쪽 위 워터마크 |
| `voice` | `ko-KR-InJoonNeural`(남) · `ko-KR-SunHiNeural`(여) · `ko-KR-HyunsuMultilingualNeural`(남) |
| `voice_rate` | 말 빠르기 `+12%` (쇼츠는 약간 빠르게) |
| `freesound_api_key` | 효과음 키 (없으면 내장 효과음) |
| `sfx_volume` / `bgm_volume` | 효과음 / 배경음 크기 |

- **배경음악**: `assets\bgm\` 에 mp3 를 넣으면 무작위로 깔립니다. (YouTube 오디오 보관함 같은 저작권 안전한 음원만)
- **이미지**: 직접 만든 이미지를 `assets\images\` 에 넣고 "이 이미지 써줘"라고 하면 카드에 들어갑니다.

## 알아둘 점
- 음성은 Microsoft Edge 의 무료 온라인 음성(edge-tts)을 씁니다. 인터넷이 필요하고, 비공식 방식이라 갑자기 막힐 수 있습니다. → 2단계에서 **내 목소리** 엔진을 붙일 예정입니다.
- 효과음은 freesound 의 **CC0(저작자 표시 불필요)** 음원만 받습니다.
- 업로드 전 `upload.txt` 의 체크리스트를 꼭 확인하세요. 수치 오류·명예훼손 책임은 올린 사람에게 있습니다.

## 문제 해결
| 증상 | 해결 |
|---|---|
| `ffmpeg 을 찾지 못했습니다` | `setup_windows.bat` 재실행 (설치 직후엔 PC 재시작이 필요할 수 있음) |
| `음성 생성 3회 실패` | 인터넷 확인 → 잠시 후 재시도 |
| 효과음이 단조로움 | freesound 키 등록 (한 번 받은 효과음은 `assets\sfx\` 에 저장돼 재사용) |
| 그 밖의 오류 | 오류 메시지를 Claude Code 에 그대로 붙여넣기 |

네트워크 없이 시험: `.venv\Scripts\python.exe make_short.py scripts\example.json --engine dummy`
