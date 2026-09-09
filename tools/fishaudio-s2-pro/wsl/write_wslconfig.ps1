$enc = New-Object System.Text.UTF8Encoding($false)
$path = 'C:\Users\RW250701\.wslconfig'
$content = @"
[wsl2]
memory=24GB
processors=16
swap=8GB
"@
[IO.File]::WriteAllText($path, $content, $enc)
Write-Host "written:"
Get-Content $path
