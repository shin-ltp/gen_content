# install-longbridge.ps1 — longbridge-terminal CLI の再現可能なインストール
# 使用方法: powershell -ExecutionPolicy Bypass -File .\install-longbridge.ps1
# 出典: https://github.com/longbridge/longbridge-terminal/releases
$ErrorActionPreference = "Stop"
$Version = "v0.26.0"
$Sha256 = "f1f3190c39ba4d7c0bbda4efc62f36e0744168b917c45b6b5f92df70e5547311"
$Url = "https://github.com/longbridge/longbridge-terminal/releases/download/$Version/longbridge-terminal-windows-amd64.zip"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Zip = Join-Path $Here "longbridge-terminal-windows-amd64.zip"
$Bin = Join-Path $Here "bin"

Invoke-WebRequest $Url -OutFile $Zip -Headers @{"User-Agent"="install-script"}
$actual = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $Sha256) { throw "SHA256 mismatch: expected $Sha256 got $actual" }
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
Expand-Archive $Zip -DestinationPath $Bin -Force
Remove-Item $Zip
& (Join-Path $Bin "longbridge.exe") --version
Write-Host "OK: $Bin\longbridge.exe"
Write-Host "Next: longbridge auth login (Device Flow) でログインすること。"
