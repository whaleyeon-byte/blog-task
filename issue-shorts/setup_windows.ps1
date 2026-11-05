# 이슈 쇼츠 메이커 - 윈도우 설치 스크립트 (setup_windows.bat 이 실행함)
# 다시 실행해도 안전합니다: 이미 설치된 건 건너뛰고, 기존 설정은 Enter 로 유지됩니다.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
Set-Location -LiteralPath $PSScriptRoot

function Step($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "   $t" -ForegroundColor Green }
function Warn($t) { Write-Host "   $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host ""; Write-Host "[실패] $t" -ForegroundColor Red; exit 1 }

function Test-Python($exe, $extra) {
    try {
        $v = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -match '^3\.(\d+)$' -and [int]$Matches[1] -ge 9) { return $true }
    } catch {}
    return $false
}

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        if (Test-Python "py" @("-3")) { return @("py", "-3") }
    }
    $c = Get-Command python -ErrorAction SilentlyContinue
    # WindowsApps\python.exe 는 스토어로 연결되는 가짜 실행 파일이라 제외
    if ($c -and $c.Source -notlike "*WindowsApps*" -and (Test-Python $c.Source @())) { return @($c.Source) }
    foreach ($ver in "313", "312", "311", "310") {
        $p = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$ver\python.exe"
        if ((Test-Path $p) -and (Test-Python $p @())) { return @($p) }
    }
    return $null
}

function Find-FFmpeg {
    $c = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $root = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $root) {
        $f = Get-ChildItem -Path $root -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue |
             Where-Object { $_.FullName -like "*Gyan.FFmpeg*" } | Select-Object -First 1
        if ($f) { return $f.FullName }
    }
    return $null
}

$hasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)

# ---------------------------------------------------------------- 1. Python
Step "1/6 파이썬 확인"
$py = Find-Python
if (-not $py) {
    if (-not $hasWinget) { Fail "파이썬이 없고 winget 도 없습니다. https://www.python.org/downloads/ 에서 설치(‘Add to PATH’ 체크) 후 다시 실행하세요." }
    Warn "파이썬 설치 중... (1~3분)"
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    $py = Find-Python
    if (-not $py) { Fail "파이썬 설치를 확인하지 못했습니다. 창을 닫고 setup_windows.bat 을 한 번 더 실행해 보세요." }
}
Ok ("사용할 파이썬: " + ($py -join " "))

# ---------------------------------------------------------------- 2. FFmpeg
Step "2/6 FFmpeg(영상 합성 프로그램) 확인"
$ff = Find-FFmpeg
if (-not $ff) {
    if (-not $hasWinget) { Fail "FFmpeg 가 없고 winget 도 없습니다. https://www.gyan.dev/ffmpeg/builds/ 에서 받아 PATH 에 추가 후 다시 실행하세요." }
    Warn "FFmpeg 설치 중... (용량이 커서 몇 분 걸릴 수 있어요)"
    winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements | Out-Host
    $ff = Find-FFmpeg
    if (-not $ff) { Fail "FFmpeg 설치를 확인하지 못했습니다. 창을 닫고 다시 실행해 보세요." }
}
Ok "FFmpeg: $ff"

# ---------------------------------------------------------------- 3. 가상환경 + 패키지
Step "3/6 프로그램 설치"
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    $exe = $py[0]; $rest = @(); if ($py.Count -gt 1) { $rest = $py[1..($py.Count - 1)] }
    & $exe @rest -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "가상환경(.venv) 생성 실패" }
}
& $venvPy -m pip install --disable-pip-version-check -q --upgrade pip
& $venvPy -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "패키지 설치 실패. 인터넷 연결을 확인하고 다시 실행하세요." }
& $venvPy -m shorts.setup_assets
Ok "프로그램 설치 완료"

# ---------------------------------------------------------------- 4~5. 설정
$cfgPath = Join-Path $PSScriptRoot "config.json"
$cfg = [ordered]@{}
if (Test-Path $cfgPath) {
    try {
        $old = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($p in $old.PSObject.Properties) { $cfg[$p.Name] = $p.Value }
    } catch { Warn "기존 config.json 을 읽지 못해 새로 만듭니다." }
}
function Ask($key, $prompt, $default) {
    $cur = if ($cfg.Contains($key) -and $cfg[$key]) { [string]$cfg[$key] } else { $default }
    $shown = if ($key -like "*key*" -and $cur) { "(저장됨)" } elseif ($cur) { "(현재: $cur)" } else { "" }
    $ans = Read-Host "$prompt $shown"
    if ([string]::IsNullOrWhiteSpace($ans)) { return $cur }
    return $ans.Trim()
}

Step "4/6 효과음 키 (선택)"
Write-Host "   freesound.org 무료 가입 → https://freesound.org/apiv2/apply 에서 API 키 발급 → 붙여넣기"
Write-Host "   건너뛰려면 Enter (내장 효과음 사용)"
$cfg["freesound_api_key"] = Ask "freesound_api_key" "   API 키:" ""

Step "5/6 채널 이름 / 목소리"
$cfg["channel_name"] = Ask "channel_name" "   채널 이름(영상 오른쪽 위 워터마크, 없으면 Enter):" ""
Write-Host "   목소리: 1) 남성 인준(차분)  2) 여성 선희(밝음)  3) 남성 현수(뉴스톤)"
$curVoice = if ($cfg.Contains("voice")) { [string]$cfg["voice"] } else { "ko-KR-InJoonNeural" }
$v = Read-Host "   번호 선택 (Enter = 현재 $curVoice 유지)"
switch ($v.Trim()) {
    "1" { $cfg["voice"] = "ko-KR-InJoonNeural" }
    "2" { $cfg["voice"] = "ko-KR-SunHiNeural" }
    "3" { $cfg["voice"] = "ko-KR-HyunsuMultilingualNeural" }
    default { $cfg["voice"] = $curVoice }
}
if (-not $cfg.Contains("voice_rate")) { $cfg["voice_rate"] = "+12%" }
$cfg["tts_engine"] = "edge"
$cfg["ffmpeg_path"] = $ff

$json = $cfg | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText($cfgPath, $json, (New-Object System.Text.UTF8Encoding($false)))
Ok "설정 저장: config.json"

# ---------------------------------------------------------------- 6. 샘플 영상
Step "6/6 설치 확인용 샘플 영상"
$ans = Read-Host "   샘플 쇼츠를 만들어 볼까요? (Y/n)"
if ($ans -notmatch '^[nN]') {
    & $venvPy make_short.py scripts\example.json
    if ($LASTEXITCODE -eq 0) {
        $last = Get-ChildItem -Path (Join-Path $PSScriptRoot "output") -Directory | Sort-Object Name -Descending | Select-Object -First 1
        if ($last) { Start-Process explorer.exe $last.FullName }
        Ok "샘플 완성! 열린 폴더의 short.mp4 를 재생해 보세요."
    } else {
        Warn "샘플 생성 실패. 위 오류 메시지를 Claude Code 에 그대로 붙여넣으면 고쳐 줍니다."
    }
}

Write-Host ""
Write-Host "== 끝" -ForegroundColor Cyan
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Warn "Claude Code 가 아직 없다면: Claude 데스크톱 앱에서 Code 탭을 쓰거나, PowerShell 에서"
    Warn "  irm https://claude.ai/install.ps1 | iex"
}
Write-Host "이제 Claude Code 에서 이 폴더를 열고 '이슈 쇼츠 만들어줘' 라고 하면 됩니다." -ForegroundColor Green
