# ADCTOX for Windows (64-bit Windows 10/11), one line in PowerShell:
#   irm https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.ps1 | iex
# No admin rights. Installs into %LOCALAPPDATA%\adctox\app, adds Start menu and desktop shortcuts and an `adctox` command,
# and downloads the models (about 1 GB) into %LOCALAPPDATA%\adctox\models. Running it again updates the app.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Manifest = if ($env:ADCTOX_WINDOWS_MANIFEST) { $env:ADCTOX_WINDOWS_MANIFEST } else { 'https://raw.githubusercontent.com/ahnhc/ADCToX/main/releases/app/windows.json' }
$Root = Join-Path $env:LOCALAPPDATA 'adctox'
$App = Join-Path $Root 'app'
$Bin = Join-Path $Root 'bin'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'ADCTOX needs 64-bit Windows.' }

$m = Invoke-RestMethod -UseBasicParsing $Manifest
if ($m.schema_version -ne 1 -or $m.url -notmatch '^https://' -or $m.sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid Windows release manifest.' }
Write-Host "Installing ADCTOX $($m.app_version) ($([math]::Round($m.size / 1MB)) MB)"
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("adctox-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $tmp | Out-Null
try {
    $zip = Join-Path $tmp 'ADCTOX-windows.zip'
    Invoke-WebRequest -UseBasicParsing $m.url -OutFile $zip
    if ((Get-Item $zip).Length -ne $m.size) { throw 'Download size mismatch; nothing was changed.' }
    if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $m.sha256) { throw 'Download checksum mismatch; nothing was changed.' }
    Expand-Archive $zip -DestinationPath $tmp
    New-Item -ItemType Directory -Force $Root | Out-Null
    if (Test-Path $App) { Remove-Item -Recurse -Force $App }
    Move-Item (Join-Path $tmp 'ADCTOX') $App
} finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }

New-Item -ItemType Directory -Force $Bin | Out-Null
Set-Content (Join-Path $Bin 'adctox.cmd') "@echo off`r`ncall `"$App\ADCTOX.bat`" %*" -Encoding ascii
$path = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($path -split ';') -notcontains $Bin) { [Environment]::SetEnvironmentVariable('Path', ($(if ($path) { "$path;" } else { '' }) + $Bin), 'User') }
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
    $lnk = $shell.CreateShortcut((Join-Path $dir 'ADCTOX.lnk'))
    $lnk.TargetPath = Join-Path $App 'ADCTOX.bat'; $lnk.WorkingDirectory = $App; $lnk.Save()
}
if ($env:ADCTOX_SKIP_MODELS -ne '1') {
    Write-Host 'Downloading the models (about 1 GB, once) ...'
    & (Join-Path $App 'python\python.exe') -I (Join-Path $App 'launcher.py') --update-models
    if ($LASTEXITCODE -ne 0) { Write-Warning 'The model download did not finish; it is retried on the first start.' }
}
Write-Host "Installed: $App"
Write-Host 'Start: the ADCTOX shortcut (Start menu or desktop), or `adctox` in a new terminal.'
