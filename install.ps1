# ADCTOX for Windows (64-bit Windows 10/11), one line in PowerShell:
#   irm https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.ps1 | iex
# No admin rights. Installs into %LOCALAPPDATA%\adctox\app, adds Start menu and desktop shortcuts and an `adctox` command,
# and downloads the models (about 300 MB) into %LOCALAPPDATA%\adctox\models. Running it again updates the app.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Manifest = if ($env:ADCTOX_WINDOWS_MANIFEST) { $env:ADCTOX_WINDOWS_MANIFEST } else { 'https://raw.githubusercontent.com/ahnhc/ADCToX/main/releases/app/windows.json' }
$Root = Join-Path $env:LOCALAPPDATA 'adctox'
$App = Join-Path $Root 'app'
$Bin = Join-Path $Root 'bin'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'ADCTOX needs 64-bit Windows.' }

function Install-Tree($New, $Target) {   # nothing is deleted until the new copy is in place; a running ADCTOX is detected first
    if (Test-Path $Target) {   # renaming a folder works even while a program in it runs, so probe the loaded files instead
        foreach ($f in Get-ChildItem $Target -Recurse -File -Include *.exe, *.dll, *.pyd -ErrorAction SilentlyContinue) {
            try { [IO.File]::Open($f.FullName, 'Open', 'ReadWrite', 'None').Dispose() }
            catch { throw "ADCTOX is running ($($f.Name) is in use). Close it, then run the installer again; nothing was changed." }
        }
    }
    $Aside = "$Target.old-" + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    Get-Item "$Target.old-*" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    $moved = Test-Path $Target
    if ($moved) { Rename-Item $Target (Split-Path $Aside -Leaf) }
    try { Move-Item $New $Target }
    catch { Remove-Item -Recurse -Force $Target -ErrorAction SilentlyContinue; if ($moved) { Rename-Item $Aside (Split-Path $Target -Leaf) }; throw }
    if ($moved) { Remove-Item -Recurse -Force $Aside -ErrorAction SilentlyContinue }
}

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
    Install-Tree (Join-Path $tmp 'ADCTOX') $App
} finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }

New-Item -ItemType Directory -Force $Bin | Out-Null
foreach ($c in @(@('adctox', ''), @('adctox-web', ' --web'), @('adctox-cli', ' --cli'))) {   # ASCII only: the app is found relative to the .cmd, so a non-ASCII account name cannot turn into ???
    Set-Content (Join-Path $Bin "$($c[0]).cmd") "@echo off`r`ncall `"%~dp0..\app\ADCTOX.bat`"$($c[1]) %*" -Encoding ascii
}
$path = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($path -split ';') -notcontains $Bin) { [Environment]::SetEnvironmentVariable('Path', ($(if ($path) { "$path;" } else { '' }) + $Bin), 'User') }
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
    $lnk = $shell.CreateShortcut((Join-Path $dir 'ADCTOX.lnk'))
    $lnk.TargetPath = Join-Path $App 'ADCTOX.bat'; $lnk.WorkingDirectory = $App; $lnk.Save()
}
if ($env:ADCTOX_SKIP_MODELS -ne '1') {
    Write-Host 'Downloading the models (about 300 MB, once) ...'
    & (Join-Path $App 'python\python.exe') -I (Join-Path $App 'launcher.py') --update-models
    if ($LASTEXITCODE -ne 0) { Write-Warning 'The model download did not finish; it is retried on the first start.' }
}
Write-Host "Installed: $App"
Write-Host 'Start: the ADCTOX shortcut (Start menu or desktop), or `adctox` in a new terminal.'
