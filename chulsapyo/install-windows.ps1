# Chulsapyo morning window - Windows installer (no admin rights needed)
# - Copies files to %LOCALAPPDATA%\Chulsapyo
# - Daily 07:00 : Task Scheduler task "Chulsapyo-Morning"
# - Every logon : shortcut in the Startup folder
$ErrorActionPreference = 'Stop'
$src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:LOCALAPPDATA 'Chulsapyo'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Force (Join-Path $src 'index.html'), (Join-Path $src 'content.js') $dest
$page = Join-Path $dest 'index.html'
$url  = ([System.Uri]$page).AbsoluteUri

# Prefer Microsoft Edge "app mode" (clean window, no tabs/address bar); fall back to default browser
$edge = @(
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($edge) {
  $exe  = $edge
  $argLine = "--app=`"$url`" --window-size=1100,860"
} else {
  $exe  = "$env:WINDIR\explorer.exe"
  $argLine = "`"$page`""
}

# 1) Daily at 07:00
$taskName = 'Chulsapyo-Morning'
$action   = New-ScheduledTaskAction -Execute $exe -Argument $argLine
$trigger  = New-ScheduledTaskTrigger -Daily -At '07:00'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
  -Description 'Shows the Chulsapyo morning advice window at 07:00' -Force | Out-Null

# 2) At every logon (Startup folder shortcut)
$startup = [Environment]::GetFolderPath('Startup')
$lnkPath = Join-Path $startup 'Chulsapyo.lnk'
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $exe
$lnk.Arguments  = $argLine
$lnk.WorkingDirectory = $dest
$lnk.Save()

Write-Host ''
Write-Host "Installed to: $dest"
Write-Host "Daily 07:00 task: $taskName"
Write-Host "Logon shortcut : $lnkPath"
Write-Host 'Opening it once now as a test...'
Start-Process -FilePath $exe -ArgumentList $argLine
