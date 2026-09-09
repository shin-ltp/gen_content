# Idempotent Windows-side launcher for the WSL2 fish-speech API server.
param(
    [ValidateSet('compile', 'eager')]
    [string]$Mode = 'compile',
    [int]$Port = 8080,
    [int]$WaitSeconds = 180
)

$ErrorActionPreference = 'Stop'

function Test-HttpReady {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Options -UseBasicParsing -TimeoutSec 3
        return $true
    } catch [Microsoft.PowerShell.Commands.HttpResponseException] {
        $code = [int]$_.Exception.Response.StatusCode
        return ($code -eq 200 -or $code -eq 404 -or $code -eq 405)
    } catch {
        return $false
    }
}

$url = "http://127.0.0.1:$Port/"
if (Test-HttpReady $url) {
    Write-Output "READY http_code=existing port=$Port"
    exit 0
}

$modeFlag = if ($Mode -eq 'compile') { '1' } else { '0' }
$polls = [Math]::Max(1, [Math]::Ceiling($WaitSeconds / 5))

$script = @"
set -u
cd /root/fish/fish-speech
old_pids=`$(pgrep -f 'tools/api_server.py' || true)
if [ -n "`$old_pids" ]; then
  kill `$old_pids 2>/dev/null || true
  sleep 1
  kill -9 `$old_pids 2>/dev/null || true
fi
: > /root/server.log
nohup env COMPILE=$modeFlag SKIP_GFX1103_FIX=1 bash /root/run_server_wsl.sh $Port > /root/server.log 2>&1 < /dev/null &
echo STARTED pid=`$!
"@

$result = wsl.exe -d Ubuntu-24.04 -u root -- bash -lc $script
if ($LASTEXITCODE -ne 0) {
    throw "wsl.exe failed with exit code $LASTEXITCODE"
}
if (-not ($result -match 'STARTED')) {
    throw "wsl.exe did not acknowledge startup: $result"
}

$ready = $false
for ($i = 0; $i -lt $polls; $i++) {
    Start-Sleep -Seconds 5
    if (Test-HttpReady $url) {
        $ready = $true
        break
    }
}

if (-not $ready) {
    $log = wsl.exe -d Ubuntu-24.04 -u root -- bash -lc "tail -30 /root/server.log"
    throw "server not ready after $WaitSeconds seconds; log tail:`n$log"
}

Write-Output "READY http_code=launched port=$Port elapsed=$((($i + 1) * 5))s"
