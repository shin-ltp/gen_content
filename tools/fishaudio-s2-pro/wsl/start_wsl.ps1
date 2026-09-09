# Fish Speech S2-Pro - WSL2 (ROCm 7.2.4 + triton) server launcher.
# Thin wrapper over the idempotent guarded launcher so interactive use and
# automation share exactly one startup contract.
param(
    [switch]$Compile,
    [switch]$SkipDequant,
    [int]$Port = 8080,
    [int]$WaitSeconds = 900
)
$ErrorActionPreference = 'Stop'

if (-not $Compile) {
    throw "Only compile mode is supported; eager mode is deprecated."
}
if (-not $SkipDequant) {
    Write-Warning "SKIP_GFX1103_FIX is always enabled by the guarded launcher."
}

$guard = Join-Path $PSScriptRoot 'start_server_guard.ps1'
& $guard -Mode compile -Port $Port -WaitSeconds $WaitSeconds
