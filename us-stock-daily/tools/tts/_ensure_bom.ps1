# Ensure UTF-8 BOM on the TTS engine scripts (project rule: all text files UTF-8 with BOM).
$files = @(
    'C:\my_project\gen-contents\us-stock-daily\tools\tts\fish_local_engine.py',
    'C:\my_project\gen-contents\us-stock-daily\tools\tts\generate_audio.py',
    'C:\my_project\gen-contents\us-stock-daily\tools\tts\_local_engine_selftest.py',
    'C:\my_project\gen-contents\us-stock-daily\tools\tts\README.md'
)
foreach ($f in $files) {
    $bytes = [IO.File]::ReadAllBytes($f)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    if (-not $hasBom) {
        $bom = [byte[]](0xEF, 0xBB, 0xBF)
        $out = New-Object byte[] ($bytes.Length + 3)
        [Array]::Copy($bom, 0, $out, 0, 3)
        [Array]::Copy($bytes, 0, $out, 3, $bytes.Length)
        [IO.File]::WriteAllBytes($f, $out)
        Write-Output "BOM added: $f"
    } else {
        Write-Output "BOM ok   : $f"
    }
}
