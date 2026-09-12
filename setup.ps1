# Creates the launcher, settings and Startup shortcuts for Nab'd.
# Re-runnable; pass -Remove to undo the autostart entry.
param([switch]$Remove)

$app = Split-Path -Parent $MyInvocation.MyCommand.Definition
$startup = [Environment]::GetFolderPath('Startup')
$startupLnk = Join-Path $startup "Nab'd.lnk"

if ($Remove) {
    if (Test-Path $startupLnk) { Remove-Item $startupLnk -Force; "removed autostart entry" }
    else { "no autostart entry found" }
    return
}

# pythonw.exe runs without a console window.
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($py) { $pyw = Join-Path (Split-Path $py) 'pythonw.exe' }
}
if (-not $pyw -or -not (Test-Path $pyw)) { throw "pythonw.exe not found" }

python (Join-Path $app 'make_ico.py')
$ico = Join-Path $app 'icon.ico'
$shell = New-Object -ComObject WScript.Shell

function New-Lnk($path, $script, $desc) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $pyw
    $lnk.Arguments = '"' + (Join-Path $app $script) + '"'
    $lnk.WorkingDirectory = $app
    $lnk.Description = $desc
    if (Test-Path $ico) { $lnk.IconLocation = $ico }
    $lnk.Save()
    "created $path"
}

New-Lnk (Join-Path $app "Nab'd.lnk")          'nabd.py'     "Nab'd - instant replay buffer"
New-Lnk (Join-Path $app "Nab'd Settings.lnk") 'settings.py' "Nab'd settings"
New-Lnk $startupLnk                            'nabd.py'     "Nab'd - instant replay buffer"

# Clean up the old pre-rename autostart entry if it is still around.
$old = Join-Path $startup 'ReplayClip.lnk'
if (Test-Path $old) { Remove-Item $old -Force; "removed old ReplayClip autostart entry" }

"`nAutostart is ON. Undo with:  powershell -File setup.ps1 -Remove"
