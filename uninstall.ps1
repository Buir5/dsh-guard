#Requires -Version 5.1
param([switch]$Purge)
$ErrorActionPreference = 'Stop'
Stop-ScheduledTask -TaskName 'dsh-guard' -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'dsh-guard' -Confirm:$false -ErrorAction SilentlyContinue
$dest = Join-Path $env:ProgramData 'dsh-guard'
if ($Purge -and (Test-Path $dest)) { Remove-Item $dest -Recurse -Force }
Write-Host 'dsh-guard removed.' -ForegroundColor Green
if (-not $Purge) { Write-Host "Backups kept at $dest (use -Purge to delete)." }