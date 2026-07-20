[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$Venv = "",
    [switch]$SkipChecks,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
if ([string]::IsNullOrWhiteSpace($Venv)) {
    $Venv = Join-Path $Root ".venv"
} elseif (-not [IO.Path]::IsPathRooted($Venv)) {
    $Venv = Join-Path $Root $Venv
}

function Write-Usage {
    @"
사용법: .\install.ps1 [-Python PATH] [-Venv PATH] [-SkipChecks]

현재 사용자용으로 Judge와 Problem Studio를 설치합니다.
  -Python PATH  Python 3.11 이상 실행 파일을 명시합니다.
  -Venv PATH    가상환경 위치를 바꿉니다(기본: 저장소\.venv).
  -SkipChecks   설치 후 doctor 점검을 건너뜁니다(자동화용).
"@
}

if ($Help -or $args -contains "--help") {
    Write-Usage
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    foreach ($Candidate in @("py", "python", "python3")) {
        $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
        if ($null -ne $Command) {
            $Python = $Command.Source
            break
        }
    }
}
if ([string]::IsNullOrWhiteSpace($Python)) {
    throw "Python 3.11 이상이 필요합니다. python.org에서 Python을 설치한 뒤 다시 실행하세요."
}

$VersionText = (& $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
$Version = [version]$VersionText
if ($Version -lt [version]"3.11") {
    throw "Python 3.11 이상이 필요합니다: $VersionText"
}

$Uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -ne $Uv) {
    Write-Host "uv 잠금 파일로 의존성을 설치합니다: $Root"
    try {
        $PreviousUvEnvironment = $env:UV_PROJECT_ENVIRONMENT
        $env:UV_PROJECT_ENVIRONMENT = $Venv
        & $Uv.Source sync --frozen --no-dev --project $Root
        if ($LASTEXITCODE -ne 0) {
            throw "uv exited with code $LASTEXITCODE"
        }
    } catch {
        Write-Warning "uv 설치가 실패해 표준 Python 가상환경으로 다시 시도합니다."
        $Uv = $null
    } finally {
        $env:UV_PROJECT_ENVIRONMENT = $PreviousUvEnvironment
    }
}
if ($null -eq $Uv) {
    Write-Host "표준 Python 가상환경을 사용합니다: $Venv"
    $VenvPython = Join-Path $Venv "Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        & $Python -m venv $Venv
    }
    try {
        & $VenvPython -m pip install --disable-pip-version-check --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            throw "pip exited with code $LASTEXITCODE"
        }
        & $VenvPython -m pip install --disable-pip-version-check --editable $Root
        if ($LASTEXITCODE -ne 0) {
            throw "pip exited with code $LASTEXITCODE"
        }
    } catch {
        throw "Python 의존성을 설치하지 못했습니다. 네트워크 또는 사내 Python mirror를 확인하세요. $_"
    }
}

$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Judge = Join-Path $Venv "Scripts\judge.exe"
$Studio = Join-Path $Venv "Scripts\problem-studio.exe"
if (-not (Test-Path $Judge) -or -not (Test-Path $Studio)) {
    throw "실행 파일을 만들지 못했습니다. '$Venv'와 설치 로그를 확인하세요."
}

if (-not $SkipChecks) {
    Write-Host "설치 후 환경을 점검합니다(컴파일러가 없으면 경고로 표시됩니다)."
    & $Judge doctor --verbose
    if ($LASTEXITCODE -ne 0) {
        throw "doctor 실행에 실패했습니다. '$Judge doctor --verbose'를 다시 실행하세요."
    }
}

Write-Host ""
Write-Host "설치가 완료되었습니다."
Write-Host "  가상환경: $Venv"
Write-Host "  Judge: $Judge"
Write-Host "  Problem Studio: $Studio"
Write-Host ""
Write-Host "다음 명령:"
Write-Host "  & `"$Judge`" web"
Write-Host "  & `"$Studio`" web"
Write-Host "  & `"$Judge`" doctor --verbose"
Write-Host ""
Write-Host "문제 팩·제출 기록은 사용자 데이터 경로에 저장됩니다. 자세한 업데이트·롤백·제거 방법은 INSTALL.md를 참고하세요."
