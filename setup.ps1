<#
  setup.ps1 - provision the bundled binaries into ./bin

  Downloads and unpacks:
    * ffmpeg + ffprobe   (gyan.dev release-essentials build; includes libx265 + zscale)
    * realesrgan-ncnn-vulkan + AI models   (xinntao Real-ESRGAN release)

  These are third-party redistributables and (for ffmpeg) exceed GitHub's
  100 MB per-file limit, so they are fetched here instead of committed.

  Usage:   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = $PSScriptRoot
$bin  = Join-Path $root "bin"
$models = Join-Path $bin "models"
$tmp  = Join-Path $env:TEMP "auvide-setup"
New-Item -ItemType Directory -Force -Path $bin, $models, $tmp | Out-Null

function Get-File($url, $dest) {
    Write-Host "  downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $dest -MaximumRedirection 5 -TimeoutSec 300
}

# ---- ffmpeg / ffprobe -------------------------------------------------
if ((Test-Path (Join-Path $bin "ffmpeg.exe")) -and (Test-Path (Join-Path $bin "ffprobe.exe"))) {
    Write-Host "[ffmpeg] already present, skipping"
} else {
    Write-Host "[ffmpeg] fetching release-essentials build ..."
    $zip = Join-Path $tmp "ffmpeg.zip"
    Get-File "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $zip
    $ex = Join-Path $tmp "ffmpeg"
    Expand-Archive -Path $zip -DestinationPath $ex -Force
    Get-ChildItem $ex -Recurse -Include ffmpeg.exe, ffprobe.exe | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $bin $_.Name) -Force
    }
    Write-Host "[ffmpeg] done"
}

# ---- realesrgan + models ---------------------------------------------
if (Test-Path (Join-Path $bin "realesrgan-ncnn-vulkan.exe")) {
    Write-Host "[realesrgan] exe already present, skipping"
} else {
    Write-Host "[realesrgan] fetching ncnn-vulkan build + models ..."
    $zip = Join-Path $tmp "realesrgan.zip"
    Get-File "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip" $zip
    $ex = Join-Path $tmp "realesrgan"
    Expand-Archive -Path $zip -DestinationPath $ex -Force
    Get-ChildItem $ex -Recurse -Include realesrgan-ncnn-vulkan.exe, *.dll | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $bin $_.Name) -Force
    }
    Get-ChildItem $ex -Recurse -Include *.param, *.bin | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $models $_.Name) -Force
    }
    Write-Host "[realesrgan] done"
}

Write-Host ""
Write-Host "bin/ contents:"
Get-ChildItem $bin -Recurse -File |
    Select-Object @{N='file';E={$_.FullName.Replace($root,'.')}},
                  @{N='MB';E={[math]::Round($_.Length/1MB,2)}} |
    Format-Table -AutoSize
Write-Host "Setup complete. Try:  python upscale_hdr.py --help"
