# 2026-08-19 Phase 3: brand logo fetching (Wikimedia Commons -> transparent PNG)
$ErrorActionPreference = 'Stop'
$brandsDir = 'D:\work\gen_content\us-stock-daily\assets\brands\companies'
New-Item -ItemType Directory -Force -Path $brandsDir | Out-Null

# slug -> Commons filename
$map = [ordered]@{
  'nvidia'        = 'NVIDIA logo.svg'
  'aapl'          = 'Apple logo black.svg'
  'microsoft'     = 'Microsoft logo (2012).svg'
  'hd'            = 'The Home Depot logo.svg'
  'tsmc'          = 'TSMC wordmark.svg'
  'meta'          = 'Meta Platforms Inc. logo.svg'
  'brk'           = 'Berkshire Hathaway.svg'
  'federal-reserve' = 'Seal of the United States Federal Reserve System.svg'
  'target'        = 'Target Corporation logo.svg'
  'walmart'       = 'Walmart logo.svg'
  'anthropic'     = 'Anthropic logo.svg'
  'coreweave'     = 'CoreWeave logo.svg'
  'cerebras'      = 'Cerebras logo.svg'
}

function Get-CommonsUrl($title, $width) {
  $q = [uri]::EscapeDataString("File:$title")
  $api = "https://commons.wikimedia.org/w/api.php?action=query&titles=$q&prop=imageinfo&iiprop=url&iiurlwidth=$width&format=json"
  $r = Invoke-RestMethod -Uri $api -TimeoutSec 30
  $page = $r.query.pages.PSObject.Properties.Value | Select-Object -First 1
  if (-not $page.imageinfo) { return $null }
  $ii = $page.imageinfo[0]
  # thumburl gives a PNG rendering for SVGs at requested width
  if ($ii.thumburl) { return $ii.thumburl }
  return $ii.url
}

foreach ($slug in $map.Keys) {
  $file = $map[$slug]
  $dest = Join-Path $brandsDir "$slug.png"
  if (Test-Path $dest) { Write-Output "[$slug] exists, skip"; continue }
  try {
    $url = Get-CommonsUrl $file 400
    if (-not $url) { Write-Output "[$slug] NOT FOUND on Commons: $file"; continue }
    Invoke-WebRequest -Uri $url -OutFile $dest -TimeoutSec 60
    $size = (Get-Item $dest).Length
    Write-Output "[$slug] OK $file -> $size bytes"
  } catch {
    Write-Output "[$slug] ERR: $($_.Exception.Message)"
  }
}
