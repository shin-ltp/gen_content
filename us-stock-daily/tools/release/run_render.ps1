param(
    [Parameter(Mandatory = $true)][string]$Date,
    [string]$Conc = '16'
)

$ErrorActionPreference = 'Stop'
if ($Date -notmatch '^\d{4}-\d{2}-\d{2}$') {
    throw "Date must be YYYY-MM-DD: $Date"
}

$usRoot = Split-Path -Parent $PSScriptRoot
$rem = Join-Path $usRoot 'remotion'
$prod = Join-Path $usRoot "daily-output\$Date\production"
$lock = Join-Path $prod 'render.lock'
$out = Join-Path $usRoot "daily-output\$Date\episode.mp4"

if (Test-Path $lock) {
    Write-Error 'render.lock exists - another render may be running'
    exit 1
}
if (Test-Path $out) {
    Write-Error 'episode.mp4 already exists - refusing to re-render'
    exit 1
}

$log = Join-Path $prod 'render_main.log'
$err = Join-Path $prod 'render_main.err.log'
Set-Content -Path $lock -Value ("PID=$PID started=" + (Get-Date -Format o))
$a = 'npx remotion render Episode "' + $out + '" --props=public/remotion_input.json --concurrency=' + $Conc + ' & del "' + $lock + '"'
$p = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $a) -WorkingDirectory $rem -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError $err
Write-Output ('render launched PID ' + $p.Id + ' date=' + $Date + ' conc=' + $Conc + ' lock=' + $lock)
