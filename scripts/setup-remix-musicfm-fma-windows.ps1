param(
  [Parameter(Mandatory=$true)][string]$ResolverReport,
  [Parameter(Mandatory=$true)][string]$NativeResolutionReceipt,
  [Parameter(Mandatory=$true)][string]$InstallLock,
  [Parameter(Mandatory=$true)][string]$AssetManifest,
  [Parameter(Mandatory=$true)][string]$Python,
  [Parameter(Mandatory=$true)][string]$FreshRoot,
  [Parameter(Mandatory=$true)][switch]$ConfirmAuthorizedSetup
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') { throw 'This handoff is native-Windows only.' }
if (-not $ConfirmAuthorizedSetup) { throw 'Explicit MusicFM setup confirmation is required.' }
if (Test-Path -LiteralPath $FreshRoot) { throw 'FreshRoot must not already exist.' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Explicit CPython path is not a file.' }
$version = (& $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if ($LASTEXITCODE -ne 0 -or -not $version.StartsWith('3.11.')) { throw 'Explicit interpreter must be CPython 3.11.' }
& $Python (Join-Path $PSScriptRoot 'validate-remix-musicfm-windows-setup-inputs.py') $ResolverReport $NativeResolutionReceipt $InstallLock $AssetManifest
if ($LASTEXITCODE -ne 0) { throw 'MusicFM setup input validation failed.' }
$report = Get-Content -Raw -LiteralPath $ResolverReport | ConvertFrom-Json
$lock = Get-Content -Raw -LiteralPath $InstallLock | ConvertFrom-Json
$assets = Get-Content -Raw -LiteralPath $AssetManifest | ConvertFrom-Json
if ($report.version -ne '1') { throw 'Unsupported pip report.' }
if ($lock.schema -ne 'sunofriend.remix-musicfm-fma-native-windows-install-lock.v0') { throw 'Wrong generated install lock.' }
if ($lock.items.Count -ne 26 -or $report.install.Count -ne 26) { throw 'Expected exactly 26 pinned packages.' }
if ($assets.schema -ne 'sunofriend.remix-musicfm-fma-asset-download-manifest.v0') { throw 'Wrong asset manifest.' }
$checkpoint = @($assets.items | Where-Object { $_.kind -eq 'checkpoint' })
if ($checkpoint.Count -ne 1 -or [int64]$checkpoint[0].bytes -ne 1316802154) { throw 'Pinned checkpoint size changed.' }

New-Item -ItemType Directory -Path $FreshRoot | Out-Null
$wheelDir = New-Item -ItemType Directory -Path (Join-Path $FreshRoot 'wheel-cache')
$assetDir = New-Item -ItemType Directory -Path (Join-Path $FreshRoot 'assets')
$licences = @()
$observedWheelBytes = [int64]0
for ($i=0; $i -lt 26; $i++) {
  $pin = $lock.items[$i]
  $url = [string]$pin.url
  $name = [Uri]::UnescapeDataString([IO.Path]::GetFileName(([Uri]$url).AbsolutePath))
  if ($name -ne $pin.filename) { throw "Wheel filename mismatch: $name" }
  $target = Join-Path $wheelDir $pin.filename
  Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing
  $observed = Get-FileHash -Algorithm SHA256 -LiteralPath $target
  if ($observed.Hash.ToLowerInvariant() -ne $pin.sha256) { throw "Wheel identity mismatch: $name" }
  $observedWheelBytes += (Get-Item $target).Length
  if ($observedWheelBytes -gt [int64]$lock.maximum_total_download_bytes) { throw 'Wheel download cap exceeded.' }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zip = [IO.Compression.ZipFile]::OpenRead($target)
  try {
    $entry = $zip.Entries | Where-Object { $_.FullName -like '*.dist-info/METADATA' } | Select-Object -First 1
    if ($null -eq $entry) { throw "Wheel lacks METADATA: $name" }
    $reader = New-Object IO.StreamReader($entry.Open())
    try { $metadata = $reader.ReadToEnd() } finally { $reader.Dispose() }
    $metadataHasher = [Security.Cryptography.SHA256]::Create()
    try {
      $metadataHash = ([BitConverter]::ToString($metadataHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($metadata)))).Replace('-', '').ToLowerInvariant()
    } finally { $metadataHasher.Dispose() }
    $licences += [pscustomobject]@{ filename=$name; metadata_sha256=$metadataHash; licence_lines=@($metadata -split "`n" | Where-Object { $_ -match '^(License|Classifier: License)' }) }
  } finally { $zip.Dispose() }
}

$observedAssetBytes = [int64]0
foreach ($item in $assets.items) {
  if ([string]::IsNullOrWhiteSpace($item.url) -or $item.sha256 -notmatch '^[0-9a-f]{64}$' -or [int64]$item.bytes -le 0) { throw 'Asset pin is incomplete.' }
  $relative = [string]$item.target_relative_path
  if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { throw 'Asset target must be safe and relative.' }
  $target = Join-Path $FreshRoot ($relative.Replace('/', '\'))
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
  Invoke-WebRequest -Uri $item.url -OutFile $target -UseBasicParsing
  if ((Get-FileHash -Algorithm SHA256 $target).Hash.ToLowerInvariant() -ne $item.sha256 -or (Get-Item $target).Length -ne [int64]$item.bytes) { throw "Asset identity mismatch: $relative" }
  $observedAssetBytes += (Get-Item $target).Length
  if ($observedAssetBytes -gt [int64]$assets.maximum_total_download_bytes) { throw 'Asset download cap exceeded.' }
}

& $Python -m venv (Join-Path $FreshRoot 'venv')
$python = Join-Path $FreshRoot 'venv\Scripts\python.exe'
$env:PIP_NO_INDEX = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$wheelFiles = @(Get-ChildItem $wheelDir -Filter '*.whl' | Sort-Object Name | ForEach-Object FullName)
if ($wheelFiles.Count -ne 26) { throw 'Verified wheel cache roster changed.' }
& $python -m pip install --no-index --no-deps @wheelFiles
if ($LASTEXITCODE -ne 0) { throw 'Offline wheel installation failed.' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Installed wheel closure failed pip check.' }
$licences | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $FreshRoot 'wheel-licence-inspection.json')
[pscustomobject]@{
  schema='sunofriend.remix-musicfm-fma-windows-setup-receipt.v0'
  packages=26
  observed_wheel_bytes=$observedWheelBytes
  observed_asset_bytes=$observedAssetBytes
  checkpoint_bytes=1316802154
  install_lock_document_sha256=$lock.document_sha256
  asset_manifest_document_sha256=$assets.document_sha256
  fresh_environment=$true
  offline_no_deps_install=$true
  model_imported=$false
  checkpoint_loaded=$false
  synthetic_canary_run=$false
  private_audio_opened=$false
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $FreshRoot 'setup-receipt.json')
