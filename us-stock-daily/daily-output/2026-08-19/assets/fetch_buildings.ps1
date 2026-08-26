# 2026-08-19 Phase 3: HQ/building photo fetch (photo-first policy)
# Sources: SearXNG images -> filter stock sites -> Wikimedia fallback
$ErrorActionPreference = 'Continue'
$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) us-stock-daily/1.0'
$brandsDir = 'D:\work\gen_content\us-stock-daily\assets\brands\companies'
$searx = 'http://127.0.0.1:8888/search'

# bad hosts: stock photo sites (watermarked/licensed), pinterest, etc.
$badHosts = @('istockphoto','shutterstock','gettyimages','getty','alamy','dreamstime',
              'adobe','depositphotos','123rf','pinterest','flickr','ebay','amazon.',
              'reddit','facebook','twitter','instagram','tiktok','youtube','linkedin')

$queries = [ordered]@{
  'nvidia-hq'        = 'NVIDIA headquarters Endeavor building Santa Clara'
  'hd-hq'            = 'Home Depot store exterior building'
  'walmart-hq'       = 'Walmart headquarters Bentonville building'
  'target-hq'        = 'Target headquarters Minneapolis building'
  'federal-reserve-hq' = 'Federal Reserve Eccles Building Washington'
  'tsmc-hq'          = 'TSMC headquarters Hsinchu building'
  'meta-hq'          = 'Meta headquarters Menlo Park building'
  'berkshire-hq'     = 'Berkshire Hathaway headquarters Omaha Kiewit Plaza'
  'apple-hq'         = 'Apple Park Cupertino headquarters'
  'microsoft-hq'     = 'Microsoft headquarters Redmond campus'
  'anthropic-hq'     = 'Anthropic office building San Francisco'
  'coreweave-hq'     = 'CoreWeave data center Livingston New Jersey'
}

function Test-BadHost([string]$url) {
  foreach ($b in $badHosts) { if ($url -match $b) { return $true } }
  return $false
}

function Get-SearxImages([string]$q) {
  $qs = "q=" + [uri]::EscapeDataString($q) + "&format=json&categories=images"
  try {
    return Invoke-RestMethod "$searx?$qs" -TimeoutSec 60
  } catch {
    Write-Output "  search ERR: $($_.Exception.Message)"
    return $null
  }
}

function Get-WikimediaUrl([string]$q, [int]$width) {
  $api = "https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch=" +
         [uri]::EscapeDataString($q) + "&srnamespace=6&srlimit=5&format=json"
  try { $r = Invoke-RestMethod $api -TimeoutSec 30 -UserAgent $ua } catch { return $null }
  foreach ($s in $r.query.search) {
    $t = $s.title
    if ($t -match '\.(jpg|jpeg|png|webp)$') {
      $qq = [uri]::EscapeDataString($t)
      $api2 = "https://commons.wikimedia.org/w/api.php?action=query&titles=$qq&prop=imageinfo&iiprop=url|size&iiurlwidth=$width&format=json"
      try {
        $r2 = Invoke-RestMethod $api2 -TimeoutSec 30 -UserAgent $ua
        $page = $r2.query.pages.PSObject.Properties.Value | Select-Object -First 1
        if ($page.imageinfo) {
          $ii = $page.imageinfo[0]
          if ($ii.thumburl -and ($page.imageinfo[0].width -gt $width)) { return $ii.thumburl }
          return $ii.url
        }
      } catch { continue }
    }
  }
  return $null
}

function Save-Image([string]$url, [string]$dest) {
  try {
    Invoke-WebRequest -Uri $url -OutFile $dest -TimeoutSec 90 -UserAgent $ua
    $sz = (Get-Item $dest).Length
    if ($sz -lt 20000) { Remove-Item $dest -Force; Write-Output "  too small ($sz B), dropped"; return $false }
    Write-Output "  saved: $([Math]::Round($sz/1KB)) KB"
    return $true
  } catch {
    Write-Output "  download ERR: $($_.Exception.Message)"
    return $false
  }
}

foreach ($slug in $queries.Keys) {
  $dest = Join-Path $brandsDir "$slug.jpg"
  if (Test-Path $dest) { Write-Output "[$slug] exists, skip"; continue }
  Write-Output "[$slug] $($queries[$slug])"
  $r = Get-SearxImages $queries[$slug]
  $done = $false
  if ($r) {
    foreach ($item in $r.results) {
      $src = [string]$item.img_src
      $page = [string]$item.url
      $hostName = ''
      try { $hostName = ([uri]$src).Host } catch { continue }
      if (-not $src) { continue }
      if (Test-BadHost $src) { continue }
      if (Test-BadHost $page) { continue }
      Write-Output "  candidate: $hostName ($($item.resolution))"
      if (Save-Image $src $dest) {
        Add-Content (Join-Path $brandsDir '_sources.log') "$slug | $src | $page | $(Get-Date -Format 'yyyy-MM-dd')"
        $done = $true; break
      }
    }
  }
  if (-not $done) {
    Write-Output "  fallback: Wikimedia Commons"
    $wurl = Get-WikimediaUrl $queries[$slug] 1600
    if ($wurl) {
      Write-Output "  commons: $wurl"
      if (Save-Image $wurl $dest) {
        Add-Content (Join-Path $brandsDir '_sources.log') "$slug | $wurl | wikimedia | $(Get-Date -Format 'yyyy-MM-dd')"
        $done = $true
      }
    }
  }
  if (-not $done) { Write-Output "  FAILED: $slug" }
  Start-Sleep 1
}
Write-Output "`n=== SUMMARY ==="
Get-ChildItem $brandsDir -Filter '*-hq.jpg' | ForEach-Object { Write-Output "$($_.Name) $([Math]::Round($_.Length/1KB)) KB" }
