# sync-collect-tools.ps1 — tools/collect と .pnpm-store 内の同一プロジェクト collect を同期する
# 使い方: powershell -ExecutionPolicy Bypass -File sync-collect-tools.ps1
$ErrorActionPreference = 'Stop'
$src = 'C:\my_project\gen-contents\us-stock-daily\tools\collect'
$dst = 'C:\my_project\gen-contents\.pnpm-store\v11\projects\4536fb21afc70f2524b358f9005a7555\collect'
if (-not (Test-Path -LiteralPath $dst)) {
  Write-Error "同期先が存在しません: $dst"
  exit 1
}
$files = @('collect-36kr.mjs','collect-all.mjs','collect-email.mjs','collect-email-imap.mjs','collect-insights.mjs','collect-longbridge.mjs','collect-rss.mjs','collect-utils.mjs','collect-wscn.mjs','seen-store.mjs','verify-collection.mjs')
foreach ($f in $files) {
  $s = [System.IO.Path]::Combine($src, $f)
  $d = [System.IO.Path]::Combine($dst, $f)
  if (-not (Test-Path -LiteralPath $s)) { Write-Warning "src に存在しない: $f"; continue }
  Copy-Item -LiteralPath $s -Destination $d -Force
  Write-Output "synced: $f"
}
Write-Output '=== done ==='
