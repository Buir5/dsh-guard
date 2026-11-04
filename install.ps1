#Requires -Version 5.1
<#
  dsh-guard installer
  Registers a SYSTEM scheduled task that keeps DeepSeek Harness bootable
  across self-updates (restores resources\runtime\office-skills).
#>
param(
    [string]$AppDir = '',
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
function Fail($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail 'run this in an elevated PowerShell (Run as Administrator)'
}

if (-not $AppDir) {
    $roots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($root in $roots) {
        $hit = Get-ItemProperty $root -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like '*DeepSeek Harness*' -and $_.InstallLocation } |
            Select-Object -First 1
        if ($hit) { $AppDir = $hit.InstallLocation.TrimEnd('\'); break }
    }
}
if (-not $AppDir) { Fail 'DeepSeek Harness not found in registry; pass -AppDir "E:\DeepSeek"' }

$asar = Join-Path $AppDir 'resources\app.asar'
if (-not (Test-Path $asar)) { Fail "app.asar not found: $asar" }

if (-not $Python) {
    $c = Join-Path $AppDir 'resources\runtime\primary-runtime\dependencies\python\pythonw.exe'
    if (Test-Path $c) { $Python = $c }
}
if (-not $Python) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python) { Fail 'pythonw.exe not found; pass -Python "...\pythonw.exe"' }

$dest = Join-Path $env:ProgramData 'dsh-guard'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# 1) install guard (rewrite the default install path baked into the script)
$src = Get-Content (Join-Path $PSScriptRoot 'dsh_guard.pyw') -Raw
$src = $src.Replace('E:\DeepSeek', $AppDir)
[IO.File]::WriteAllText((Join-Path $dest 'dsh_guard.pyw'), $src, (New-Object Text.UTF8Encoding($false)))

# 2) build the stash of SKILL.md files
$stash = Join-Path $dest 'office-skills'
$rt = Join-Path $AppDir 'resources\runtime\office-skills'
if (Test-Path (Join-Path $rt 'office\SKILL.md')) {
    Copy-Item (Join-Path $rt '*') $stash -Recurse -Force
    Write-Host "[1/3] stash copied from runtime ($((Get-ChildItem $stash -Recurse -File).Count) files)"
} else {
    & $Python (Join-Path $PSScriptRoot 'tools\build_stash.py') --asar $asar --out $stash
    if ($LASTEXITCODE -ne 0) { Fail 'failed to extract assets from app.asar' }
    Write-Host "[1/3] stash extracted from app.asar"
}

# 3) scheduled task
$act = New-ScheduledTaskAction -Execute $Python -Argument ('"' + (Join-Path $dest 'dsh_guard.pyw') + '"')
$trg = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn))
$prn = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'dsh-guard' -Action $act -Trigger $trg -Principal $prn -Settings $set -Force | Out-Null
Start-ScheduledTask -TaskName 'dsh-guard'
Start-Sleep -Seconds 2
$st = (Get-ScheduledTask -TaskName 'dsh-guard').State
Write-Host "[2/3] task registered: dsh-guard ($st, SYSTEM, AtStartup + AtLogOn)"
Write-Host "[3/3] log: $(Join-Path $dest 'guard.log')"
Write-Host ''
Write-Host 'Done. Verify: rename resources\runtime\office-skills, it must come back within ~2s.' -ForegroundColor Green