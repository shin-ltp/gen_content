# Retry failed logos with proper UA + delay (Wikimedia rate limits)
$ErrorActionPreference = 'Continue'
$brandsDir = 'D:\work\gen_content\us-stock-daily\assets\brands\companies'
$ua = 'us-stock-daily-research-bot/1.0 (content-production; contact: local)'

$map = [ordered]@{
  'hd'              = 'The Home Depot logo.svg'
  'meta'            = 'Meta Platforms Inc. logo.svg'
  'brk'             = 'Berkshire Hathaway.svg'
  'federal-reserve' = 'Seal of the United States Federal Reserve System.svg'
  'target'          = 'Target Corporation logo.svg'
  'walmart'         = 'Walmart logo.svg'
  'coreweave'       = 'CoreWeave logo.svg'
  'cerebras'        = 'Cerebras logo.svg'
}

function Invoke-WithUa($uri, $out) {
  Invoke-WebRequest -Uri $uri -OutFile $out -TimeoutSec 60 -UserAgent $ua
}

function Get-CommonsUrl($title, $width) {
  $q = [uri]::EscapeDataString("File:$title")
  $api = "https://commons.wikimedia.org/w/api.php?action=query&titles=$q&prop=imageinfo&iiprop=url&iiurlwidth=$width&format=json"
  $r = Invoke-RestMethod -Uri $api -TimeoutSec 30 -UserAgent $ua
  $page = $r.query.pages.PSObject.Properties.Value | Select-Object -First 1
  if (-not $page.imageinfo) { return $null }
  $ii = $page.imageinfo[0]
  if ($ii.thumburl) { return $ii.thumburl }
  return $ii.url
}

foreach ($slug in $map.Keys) {
  $dest = Join-Path $brandsDir "$slug.png"
  if (Test-Path $dest) { Write-Output "[$slug] exists, skip"; Start-Sleep 2; continue }
  $ok = $false
  foreach ($attempt in 1..3) {
    try {
      $url = Get-CommonsUrl $map[$slug] 400
      if (-not $url) { Write-Output "[$slug] NOT FOUND: $($map[$slug])"; break }
      Invoke-WithUa $url $dest
      $size = (Get-Item $dest).Length
      Write-Output "[$slug] OK attempt=$attempt $size bytes"
      $ok = $true
      break
    } catch {
      Write-Output "[$slug] attempt=$attempt failed: $($_.Exception.Message)"
      Start-Sleep 8
    }
  }
  Start-Sleep 3
}
Write-Output "--- verify header bytes ---"
foreach ($slug in $map.Keys) {
  $dest = Join-Path $brandsDir "$slug.png"
  if (Test-Path $dest) {
    $b = [byte[]](Get-Content $dest -Encoding Byte -TotalCount 4)
    $hex = ($b | ForEach-Object { $_.ToString('X2') }) -join ' '
    Write-Output "[$slug] first4=$hex size=$((Get-Item $dest).Length)"
  } else {
    Write-Output "[$slug] MISSING"
  }
}
