# Idempotent Windows-side launcher for the WSL2 fish-speech API server.
param(
    [ValidateSet('compile', 'eager')]
    [string]$Mode = 'compile',
    [int]$Port = 18790,
    [int]$WaitSeconds = 180,
    [string]$PipelineDate = '',
    [switch]$NoWait
)

$ErrorActionPreference = 'Stop'

# Cron startup must not serialize collection behind a slow engine compile.
if ($NoWait) {
    $childArgs = @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', $PSCommandPath,
        '-Mode', $Mode, '-Port', $Port, '-WaitSeconds', $WaitSeconds
    )
    if ($PipelineDate) { $childArgs += @('-PipelineDate', $PipelineDate) }
    $child = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList $childArgs -WindowStyle Hidden -PassThru
    Write-Output "STARTED_ASYNC pid=$($child.Id) port=$Port"
    exit 0
}

$RuntimeRoot = Join-Path $PSScriptRoot '..\..\..\.runtime\tts-engine'
$LockPath = Join-Path $RuntimeRoot 'locks\server-guard.lock'
$ProgressPath = Join-Path $RuntimeRoot 'engine-progress.json'
$KeeperPidPath = Join-Path $RuntimeRoot 'keeper.pid'
$LockTtlSeconds = [Math]::Max(1800, $WaitSeconds + 600)
$StartedAt = Get-Date

# Bookkeeping into daily pipeline.json; never breaks engine startup.
function Set-EngineState {
    param([string]$State, [string]$Note = '')
    if (-not $PipelineDate -or $PipelineDate -notmatch '^\d{4}-\d{2}-\d{2}$') { return }
    $pipeline = Join-Path $PSScriptRoot '..\..\..\us-stock-daily\tools\pipeline\pipeline.mjs'
    if (-not (Test-Path $pipeline)) { return }
    try {
        $noteArg = @()
        if ($Note) { $noteArg = @('--note', $Note) }
        & node $pipeline engine --date $PipelineDate --state $State @noteArg 2>$null | Out-Null
    } catch { }
}

function Write-JsonFile {
    param([string]$Path, [object]$Value)
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, (ConvertTo-Json $Value -Depth 4 -Compress), $utf8)
}

function Set-ProgressState {
    param(
        [string]$Phase,
        [string]$Message = '',
        [bool]$HttpReady = $false,
        [string]$Unit = '',
        [string]$ApiPid = '',
        [string]$LogTail = '',
        [int]$KeeperPid = 0
    )
    $state = [ordered]@{
        updated_at = (Get-Date).ToString('o')
        guard_pid = $PID
        mode = $Mode
        port = $Port
        phase = $Phase
        message = $Message
        http_ready = $HttpReady
        unit = $Unit
        api_pid = $ApiPid
        elapsed_seconds = [int]((Get-Date) - $StartedAt).TotalSeconds
        wait_budget_seconds = $WaitSeconds
        log_tail = $LogTail
        keeper_pid = $KeeperPid
        pipeline_date = $PipelineDate
    }
    try { Write-JsonFile -Path $ProgressPath -Value $state } catch { }
}

function Test-PidAlive {
    param([int]$ProcessId, [string]$ExpectedName = '')
    if ($ProcessId -le 0) { return $false }
    $p = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    if ($ExpectedName -and $p.ProcessName -ne $ExpectedName) { return $false }
    return $true
}

# WSL2 shuts the distro down when its last wsl.exe client disappears.  A
# long-lived hidden client is the reliable way to protect a systemd unit while
# fish-speech is compiling.
function Ensure-Keeper {
    $old = 0
    try {
        if (Test-Path $KeeperPidPath) {
            $old = [int](Get-Content $KeeperPidPath -TotalCount 1)
        }
    } catch { }
    if (Test-PidAlive -ProcessId $old -ExpectedName 'wsl') {
        return $old
    }

    $keeper = Start-Process -FilePath 'wsl.exe' `
        -ArgumentList @('-d', 'Ubuntu-24.04', '-u', 'root', '--', 'sleep', 'infinity') `
        -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 1
    if (-not (Test-PidAlive -ProcessId $keeper.Id -ExpectedName 'wsl')) {
        throw "failed to start WSL keeper (pid=$($keeper.Id))"
    }
    Write-JsonFile -Path $KeeperPidPath -Value $keeper.Id
    return $keeper.Id
}

function Test-HttpReady {
    param([string]$Url)
    try {
        Invoke-WebRequest -Uri $Url -Method Options -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        # PS5.1 では例外型が WebException (Response 付き)、PS7 では HttpResponseException。
        # 型名 catch は PS5.1 で TypeNotFound になるため共通の例外検査にする。
        $code = 0
        try { $code = [int]$_.Exception.Response.StatusCode } catch { }
        return ($code -eq 200 -or $code -eq 204 -or $code -eq 404 -or $code -eq 405)
    }
}

function Get-ServerSnapshot {
    $cmd = @'
printf 'unit=%s\napi_pid=%s\n' "$(systemctl is-active fishtts 2>/dev/null || true)" "$(pgrep -f 'tools/api_server.py' | head -n1)"
tail -n 2 /root/server.log 2>/dev/null || true
'@
    return @(wsl.exe -d Ubuntu-24.04 -u root -- bash -lc $cmd)
}

function Update-SnapshotProgress {
    param([string]$Phase, [string]$Message, [bool]$HttpReady)
    $snapshot = Get-ServerSnapshot
    $unit = ''
    $apiPid = ''
    $logLines = @()
    foreach ($line in $snapshot) {
        if ($null -eq $line) { continue }
        $text = "$line"
        if ($text.StartsWith('unit=')) { $unit = $text.Substring(5) }
        elseif ($text.StartsWith('api_pid=')) { $apiPid = $text.Substring(8) }
        elseif ($text.Trim().Length -gt 0) { $logLines += $text }
    }
    $tail = ($logLines | Select-Object -Last 2) -join ' | '
    Set-ProgressState -Phase $Phase -Message $Message -HttpReady:$HttpReady `
        -Unit $unit -ApiPid $apiPid -LogTail $tail -KeeperPid $keeperPid
    return @{
        unit = $unit
        api_pid = $apiPid
        log_tail = (($logLines | Select-Object -Last 30) -join "`n")
    }
}

$url = "http://127.0.0.1:$Port/v1/tts"
$keeperPid = Ensure-Keeper

if (Test-HttpReady $url) {
    Update-SnapshotProgress -Phase 'ready' -Message 'existing server' -HttpReady:$true | Out-Null
    Write-Output "READY http_code=existing port=$Port"
    Set-EngineState -State 'ready' -Note 'existing server'
    exit 0
}

# One synchronous guard at a time.  A stale lock older than the compile budget
# is reclaimed so a crashed child cannot block recovery forever.
if (Test-Path $LockPath) {
    $lockAge = $null
    try {
        $lockAge = [int]((Get-Date) - (Get-Item $LockPath).LastWriteTime).TotalSeconds
    } catch { }
    if ($null -ne $lockAge -and $lockAge -lt $LockTtlSeconds) {
        Update-SnapshotProgress -Phase 'busy' `
            -Message "another guard is starting the engine (lock_age=${lockAge}s)" `
            -HttpReady:$false | Out-Null
        Write-Output "GUARD_BUSY lock_age=${lockAge}s port=$Port"
        Set-EngineState -State 'starting' -Note "guard busy; lock_age=${lockAge}s"
        exit 0
    }
}
New-Item -ItemType Directory -Path (Split-Path -Parent $LockPath) -Force | Out-Null
Set-Content -Path $LockPath -Value "pid=$PID started=$((Get-Date).ToString('o'))" -Encoding Ascii

try {
    $modeFlag = if ($Mode -eq 'compile') { '1' } else { '0' }
    $polls = [Math]::Max(1, [Math]::Ceiling($WaitSeconds / 5))
    Update-SnapshotProgress -Phase 'checking' -Message 'checking existing WSL unit' `
        -HttpReady:$false | Out-Null

    $script = @"
set -u
cd /root/fish/fish-speech
if systemctl is-active --quiet fishtts 2>/dev/null; then
  echo ALREADY
  exit 0
fi
old_pids=`$(pgrep -f 'tools/api_server.py' || true)
if [ -n "`$old_pids" ]; then
  kill `$old_pids 2>/dev/null || true
  sleep 1
  kill -9 `$old_pids 2>/dev/null || true
fi
# systemd transient unit: keeps the engine alive after this WSL session ends
systemctl stop fishtts 2>/dev/null || true
systemctl reset-failed fishtts 2>/dev/null || true
systemd-run --unit=fishtts --collect --property=StandardOutput=append:/root/server.log --property=StandardError=append:/root/server.log env COMPILE=$modeFlag SKIP_GFX1103_FIX=1 bash /root/run_server_wsl.sh $Port
echo STARTED
"@

    $result = wsl.exe -d Ubuntu-24.04 -u root -- bash -lc $script
    if ($LASTEXITCODE -ne 0) {
        Update-SnapshotProgress -Phase 'failed' -Message "wsl.exe exit $LASTEXITCODE" `
            -HttpReady:$false | Out-Null
        Set-EngineState -State 'failed' -Note "wsl.exe exit $LASTEXITCODE"
        throw "wsl.exe failed with exit code $LASTEXITCODE"
    }
    if (-not ($result -match 'STARTED')) {
        if ($result -match 'ALREADY') {
            Write-Output "ALREADY unit=fishtts port=$Port (waiting for existing compile/startup)"
            Set-EngineState -State 'starting' -Note 'existing unit; guard waiting'
            $WaitSeconds = [Math]::Max($WaitSeconds, 900)
            $polls = [Math]::Max(1, [Math]::Ceiling($WaitSeconds / 5))
        } else {
            Update-SnapshotProgress -Phase 'failed' -Message 'no STARTED ack' `
                -HttpReady:$false | Out-Null
            Set-EngineState -State 'failed' -Note 'no STARTED ack'
            throw "wsl.exe did not acknowledge startup: $result"
        }
    }
    Set-EngineState -State 'starting' -Note 'wsl start acknowledged; see engine-progress.json'

    $ready = $false
    for ($i = 0; $i -lt $polls; $i++) {
        Start-Sleep -Seconds 5
        if (Test-HttpReady $url) {
            $ready = $true
            break
        }
        if (($i % 3) -eq 2) {
            Update-SnapshotProgress -Phase 'starting' `
                -Message "waiting for API; elapsed=$((($i + 1) * 5))s" `
                -HttpReady:$false | Out-Null
        }
    }

    if (-not $ready) {
        $snapshot = Update-SnapshotProgress -Phase 'failed' `
            -Message "not ready after $WaitSeconds s" -HttpReady:$false
        $log = $snapshot.log_tail
        Set-EngineState -State 'failed' -Note "not ready after $WaitSeconds s"
        throw "server not ready after $WaitSeconds seconds; log tail:`n$log"
    }

    Update-SnapshotProgress -Phase 'ready' -Message 'API is ready' -HttpReady:$true | Out-Null
    Write-Output "READY http_code=launched port=$Port elapsed=$((($i + 1) * 5))s"
    Set-EngineState -State 'ready' -Note "launched in $(($i + 1) * 5)s"
} finally {
    Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
}
