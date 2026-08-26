# Retry building photos: fix output capture bug, add delays + query variants
$ErrorActionPreference = 'Continue'
$ua = 'us-stock-daily-asset-fetch/1.0 (research; contact local)'
$brandsDir = 'D:\work\gen_content\us-stock-daily\assets\brands\companies'
$searx = 'http://127.0.0.1:8888/search'

$badHosts = @('istockphoto','shutterstock','gettyimages','getty','alamy','dreamstime',
              'adobe','depositphotos','123rf','pinterest','flickr','ebay','amazon.',
              'reddit','facebook','twitter','instagram','tiktok','youtube','linkedin',
              'wallpaper','clipart','pngtree','cleanpng','pngegg','seeklogo','logotyp',
              'worldvectorlogo','brandsoftheworld','vectorseek','svgrepo','wikia','fandom')

$plan = [ordered]@{
  'walmart-hq'       = @('Walmart headquarters Bentonville building')
  'target-hq'        = @('Target headquarters Minneapolis building')
  'federal-reserve-hq' = @('Federal Reserve Eccles Building Washington')
  'meta-hq'          = @('Meta headquarters Menlo Park building')
  'hd-hq'            = @('Home Depot store exterior','The Home Depot building Atlanta')
  'tsmc-hq'          = @('TSMC headquarters Hsinchu','TSMC building Taiwan')
  'berkshire-hq'     = @('Kiewit Plaza Omaha','Berkshire Hathaway Omaha building')
  'apple-hq'         = @('Apple Park Cupertino aerial','Apple Park visitor center')
  'microsoft-hq'     = @('Microsoft Redmond campus building','Microsoft headquarters sign')
  'anthropic-hq'     = @('Anthropic San Francisco office','Anthropic building')
  'coreweave-hq'     = @('CoreWeave data center','CoreWeave building')
}

# known-good commons URLs (from prior run) — retry downloads with delay
$known = [ordered]@{
  'walmart-hq' = 'https://upload.wikimedia.org/wikipedia/commons/b/ba/Walmart_Home_Office_Bentonville%2C_Arkansas.jpg'
  'target-hq' = 'https://upload.wikimedia.org/wikipedia/commons/thumb/8/8d/Target_Headquarters%2C_Ukraine_support_%285190339647%29.jpg/1920px-Target_Headquarters%2C_Ukraine_support_%285190339647%29.jpg'
  'federal-reserve-hq' = 'https://upload.wikimedia.org/wikipedia/commons/thumb/8/89/Eccles_Building_%2826088200676%29.jpg/1920px-Eccles_Building_%2826088200676%29.jpg'
  'meta-hq' = 'https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/Meta_HQ_2023.png/1920px-Meta_HQ_2023.png'
}

function Test-BadHost([string]$url) {
  foreach ($b in $badHosts) { if ($url -match [regex]::Escape($b)) { return $true } }
  return $false
}

function Download-Img([string]$url, [string]$dest) {
  # returns [bool]; diagnostics via Write-Host (never captured by callers)
  try {
    Invoke-WebRequest -Uri $url -OutFile $dest -TimeoutSec 90 -UserAgent $ua -ErrorAction Stop
    $sz = (Get-Item $dest).Length
    if ($sz -lt 15000) { Remove-Item $dest -Force; Write-Host "  too small ($sz B), dropped"; return $false }
    Write-Host "  saved: $([Math]::Round($sz/1KB)) KB"
    return $true
  } catch {
    Write-Host "  download ERR: $($_.Exception.Message)"
    return $false
  }
}

function Get-CommonsFile([string]$q, [int]$width) {
  $api = "https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch=" +
         [uri]::EscapeDataString($q) + "&srnamespace=6&srlimit=6&format=json"
  try { $r = Invoke-RestMethod $api -TimeoutSec 30 -UserAgent $ua -ErrorAction Stop } catch { Write-Host "  commons search ERR: $($_.Exception.Message)"; return $null }
  Start-Sleep 2
  foreach ($s in $r.query.search) {
    $t = [string]$s.title
    if ($t -notmatch '\.(jpg|jpeg|png|webp)$') { continue }
    $qq = [uri]::EscapeDataString($t)
    $api2 = "https://commons.wikimedia.org/w/api.php?action=query&titles=$qq&prop=imageinfo&iiprop=url|size&iiurlwidth=$width&format=json"
    try {
      $r2 = Invoke-RestMethod $api2 -TimeoutSec 30 -UserAgent $ua -ErrorAction Stop
      Start-Sleep 2
      $page = $r2.query.pages.PSObject.Properties.Value | Select-Object -First 1
      if ($page.imageinfo) {
        $ii = $page.imageinfo[0]
        if ($ii.thumburl -and $ii.width -gt $width) { return @($ii.thumburl, $t) }
        return @($ii.url, $t)
      }
    } catch { Start-Sleep 2; continue }
  }
  return $null
}

foreach ($slug in $plan.Keys) {
  $dest = Join-Path $brandsDir "$slug.jpg"
  if (Test-Path $dest) { Write-Host "[$slug] exists, skip"; continue }
  Write-Host "=== [$slug] ==="
  $ok = $false

  # 1) known commons URL retry
  if ($known.Contains($slug)) {
    Write-Host "  retry known commons URL"
    $r = Download-Img $known[$slug] $dest
    if ($r -eq $true) { $ok = $true; Add-Content (Join-Path $brandsDir '_sources.log') "$slug | $($known[$slug]) | wikimedia-known | $(Get-Date -Format 'yyyy-MM-dd')" }
  }

  # 2) SearXNG images
  if (-not $ok) {
    foreach ($q in $plan[$slug]) {
      $qs = "q=" + [uri]::EscapeDataString($q) + "&format=json&categories=images"
      try { $resp = Invoke-RestMethod "$searx?$qs" -TimeoutSec 60 -ErrorAction Stop } catch { Write-Host "  searx ERR: $($_.Exception.Message)"; continue }
      $cands = @($resp.results) | Where-Object {
        $_.img_src -and -not (Test-BadHost $_.img_src) -and -not (Test-BadHost ([string]$_.url)) -and
        $_.resolution -match '^(\d+)' -and [int]($_.resolution -split 'x')[0] -ge 800
      }
      Write-Host "  searx '$q': $(@($resp.results).Count) raw, $($cands.Count) candidates"
      foreach ($c in $cands) {
        Write-Host "  try: $(([uri]$c.img_src).Host) ($($c.resolution))"
        $r = Download-Img ([string]$c.img_src) $dest
        if ($r -eq $true) {
          $ok = $true
          Add-Content (Join-Path $brandsDir '_sources.log') "$slug | $($c.img_src) | $($c.url) | $(Get-Date -Format 'yyyy-MM-dd')"
          break
        }
        Start-Sleep 1
      }
      if ($ok) { break }
      Start-Sleep 2
    }
  }

  # 3) Commons search variants
  if (-not $ok) {
    foreach ($q in $plan[$slug]) {
      Write-Host "  commons search: $q"
      $f = Get-CommonsFile $q 1600
      if ($f) {
        Write-Host "  commons file: $($f[1])"
        $r = Download-Img $f[0] $dest
        if ($r -eq $true) { $ok = $true; Add-Content (Join-Path $brandsDir '_sources.log') "$slug | $($f[0]) | wikimedia-search($q) | $(Get-Date -Format 'yyyy-MM-dd')"; break }
      }
      Start-Sleep 3
    }
  }

  if (-not $ok) { Write-Host "  FAILED: $slug" }
}
Write-Host "`n=== CURRENT HQ FILES ==="
Get-ChildItem $brandsDir -Filter '*-hq.*' | ForEach-Object { Write-Host "$($_.Name) $([Math]::Round($_.Length/1KB)) KB" }
