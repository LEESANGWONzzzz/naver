# Chulsapyo morning window - Windows uninstaller
$ErrorActionPreference = 'SilentlyContinue'
Unregister-ScheduledTask -TaskName 'Chulsapyo-Morning' -Confirm:$false
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath('Startup')) 'Chulsapyo.lnk')
Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA 'Chulsapyo')
Write-Host 'Chulsapyo removed.'
