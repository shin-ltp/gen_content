# search.ps1 - SearXNG query tool for Phase 0 collector (us-stock-daily)
# Reads config from ../../.env: SEARXNG_BASE_URL (required),
# SEARXNG_USER / SEARXNG_PASSWORD (optional - Basic Auth only sent when both are set).
# Usage:
#   .\search.ps1 -Check                                  # toolchain health check (exit 0/1)
#   .\search.ps1 "Nvidia AI chip"                        # defaults: news / day
#   .\search.ps1 "ISM services PMI" -Categories general,news -TimeRange week
#   .\search.ps1 "日経平均 最高値" -Language ja-JP -MaxResults 5
#   .\search.ps1 "Palantir" -Raw                         # raw JSON
#   .\search.ps1 "Berkshire Q2" -OutFile results.json    # save raw JSON (UTF-8 no BOM)
param(
    [Parameter(Position=0)][string]$Query = "",
    [string]$Categories = "news",
    [string]$TimeRange  = "day",
    [string]$Language   = "",
    [string]$Engines    = "",
    [int]$MaxResults    = 10,
    [string]$OutFile    = "",
    [switch]$Raw,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

# --- load .env ---------------------------------------------------------
$envFile = Join-Path $PSScriptRoot "..\..\.env"
if (-not (Test-Path $envFile)) { Write-Error ".env not found: $envFile"; exit 1 }
$cfg = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$') { $cfg[$matches[1]] = $matches[2] }
}
if (-not $cfg["SEARXNG_BASE_URL"]) { Write-Error "SEARXNG_BASE_URL missing in .env"; exit 1 }
$base = $cfg["SEARXNG_BASE_URL"].TrimEnd('/')
$headers = @{}
if ($cfg["SEARXNG_USER"] -and $cfg["SEARXNG_PASSWORD"]) {
    $auth = "Basic " + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$($cfg['SEARXNG_USER']):$($cfg['SEARXNG_PASSWORD'])"))
    $headers["Authorization"] = $auth
}

# --- ensure instance is running (local auto-start) -----------------------
function Test-SearXngUp {
    try {
        $hz = Invoke-WebRequest "$base/healthz" -UseBasicParsing -TimeoutSec 5
        return ($hz.StatusCode -eq 200)
    } catch { return $false }
}

function Ensure-SearXngRunning {
    if (Test-SearXngUp) { return }
    # Auto-start only applies to the local instance; remote endpoints just fail.
    if ($base -notmatch '^https?://(127\.0\.0\.1|localhost)(:\d+)?') {
        Write-Error "SearXNG not responding at $base (remote endpoint - no auto-start)."
        exit 1
    }
    Write-Host "SearXNG not responding at $base - attempting docker compose auto-start..."
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "docker not found in PATH. Start Docker Desktop, or start SearXNG manually."
        exit 1
    }
    # docker writes progress to stderr; keep EAP=Stop from treating it as a fatal error
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location $PSScriptRoot
    docker compose up -d 2>&1 | Out-Null
    $rc = $LASTEXITCODE
    Pop-Location
    $ErrorActionPreference = $prevEAP
    if ($rc -ne 0) {
        Write-Error "Auto-start failed (docker compose up -d exit $rc). Is Docker Desktop running?"
        exit 1
    }
    $ok = $false
    foreach ($i in 1..20) {
        Start-Sleep -Seconds 3
        if (Test-SearXngUp) { $ok = $true; break }
    }
    if (-not $ok) {
        Write-Error "SearXNG not healthy within 60s after auto-start. Check: docker logs searxng"
        exit 1
    }
    Write-Host "SearXNG auto-started."
}

Ensure-SearXngRunning

# --- health check mode --------------------------------------------------
if ($Check) {
    $ok = $true
    try {
        $hz = Invoke-WebRequest "$base/healthz" -UseBasicParsing -TimeoutSec 10
        Write-Host "healthz: $($hz.Content)"
    } catch { Write-Host "healthz FAILED: $($_.Exception.Message)"; $ok = $false }
    try {
        $r = Invoke-RestMethod "$base/search?q=stock&format=json" -Headers $headers -TimeoutSec 45
        $n = @($r.results).Count
        Write-Host "search+auth: OK ($n results)"
        if ($n -eq 0) { Write-Host "WARNING: 0 results - engines may be blocked"; $ok = $false }
    } catch { Write-Host "search+auth FAILED: $($_.Exception.Message)"; $ok = $false }
    if ($ok) { exit 0 } else { exit 1 }
}

if (-not $Query) { Write-Error "Query required (or use -Check)"; exit 1 }

# --- build query URL ----------------------------------------------------
$qs = "q=" + [uri]::EscapeDataString($Query) + "&format=json"
if ($Categories) { $qs += "&categories=" + [uri]::EscapeDataString($Categories) }
if ($TimeRange)  { $qs += "&time_range=" + [uri]::EscapeDataString($TimeRange) }
if ($Language)   { $qs += "&language=" + [uri]::EscapeDataString($Language) }
if ($Engines)    { $qs += "&engines=" + [uri]::EscapeDataString($Engines) }
$url = "$base/search?$qs"

# --- request -------------------------------------------------------------
# bing intermittently throttles bursty queries from DC IPs (upstream hangs past
# nginx's 30s read timeout). One retry with a pause covers the common case.
$resp = $null
foreach ($attempt in 1..2) {
    try {
        $resp = Invoke-RestMethod $url -Headers $headers -TimeoutSec 60
        break
    } catch {
        if ($attempt -eq 1) {
            Write-Host "request failed ($($_.Exception.Message)); retrying in 6s..."
            Start-Sleep -Seconds 6
        } else {
            Write-Error "SearXNG request failed after retry: $($_.Exception.Message)"
            exit 1
        }
    }
}

if ($OutFile) {
    $json = $resp | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText((Resolve-Path -LiteralPath (Split-Path $OutFile -Parent)).Path + "\" + (Split-Path $OutFile -Leaf), $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "saved: $OutFile"
}

if ($Raw) { $resp | ConvertTo-Json -Depth 10; exit 0 }

# --- formatted output -----------------------------------------------------
$results = @($resp.results) | Select-Object -First $MaxResults
Write-Host "query: $($resp.query) | results: $(@($resp.results).Count) | showing: $($results.Count)"
$unresp = @($resp.unresponsive_engines)
if ($unresp.Count -gt 0) { Write-Host "unresponsive engines: $($unresp -join '; ')" }
$i = 0
foreach ($r in $results) {
    $i++
    $meta = ""
    if ($r.metadata)  { $meta = " | " + $r.metadata }
    if ($r.publishedDate) { $meta += " | pub: " + $r.publishedDate }
    Write-Host ""
    Write-Host "[$i] $($r.title)"
    Write-Host "    url: $($r.url)"
    if ($meta) { Write-Host "    meta:$meta" }
    if ($r.content) { Write-Host ("    " + ($r.content -replace '\s+',' ').Substring(0, [Math]::Min(220, $r.content.Length))) }
}
