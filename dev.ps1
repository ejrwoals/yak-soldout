# yak-soldout dev 환경 실행 스크립트 (Windows PowerShell)
# 사용법: .\dev.ps1

Set-Location $PSScriptRoot

$VenvPython = ".venv\Scripts\python.exe"
$env:PORT = "8002"

# 1) .venv 확인
if (-not (Test-Path $VenvPython)) {
    Write-Host "❌ $VenvPython 을 찾을 수 없습니다."
    Write-Host "   먼저 'uv venv' 로 가상환경을 만들고 의존성을 설치하세요."
    exit 1
}

# 2) 해당 포트를 점유 중인 좀비 프로세스 정리
$Zombies = netstat -ano | Select-String ":$($env:PORT)\s.*LISTENING" | ForEach-Object {
    ($_ -split '\s+')[-1]
} | Select-Object -Unique

if ($Zombies) {
    Write-Host "⚠️  포트 $($env:PORT) 점유 프로세스 정리: $($Zombies -join ', ')"
    foreach ($pid in $Zombies) {
        try { Stop-Process -Id $pid -Force -ErrorAction Stop } catch {}
    }
    Start-Sleep -Seconds 1
}

# 3) 서버 실행
& $VenvPython web_server.py
