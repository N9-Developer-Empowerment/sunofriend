param(
  [Parameter(Mandatory=$true)][string]$Request,
  [Parameter(Mandatory=$true)][string]$TrainingSnapshot,
  [Parameter(Mandatory=$true)][string]$RuntimeRoot,
  [Parameter(Mandatory=$true)][string]$FreshStagingRoot,
  [Parameter(Mandatory=$true)][string]$ControlAudio,
  [Parameter(Mandatory=$true)][string]$LeftAudio,
  [Parameter(Mandatory=$true)][string]$RightAudio,
  [Parameter(Mandatory=$true)][switch]$ConfirmAuthorizedExtraction
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') { throw 'This handoff is native-Windows only.' }
if (-not $ConfirmAuthorizedExtraction) { throw 'Explicit private feature-extraction confirmation is required.' }
if (Test-Path -LiteralPath $FreshStagingRoot) { throw 'FreshStagingRoot must not already exist.' }
if ([IO.Path]::GetFullPath($FreshStagingRoot) -match '(?i)OneDrive') { throw 'Private staging must be outside OneDrive.' }
foreach ($path in @($Request, $TrainingSnapshot, $ControlAudio, $LeftAudio, $RightAudio)) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required input is missing: $path" }
}
$python = Join-Path $RuntimeRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Pinned MusicFM Python runtime is missing.' }

$inputRoot = New-Item -ItemType Directory -Path (Join-Path $FreshStagingRoot 'inputs') -Force
Copy-Item -LiteralPath $ControlAudio -Destination (Join-Path $inputRoot 'control.wav')
Copy-Item -LiteralPath $LeftAudio -Destination (Join-Path $inputRoot 'left.wav')
Copy-Item -LiteralPath $RightAudio -Destination (Join-Path $inputRoot 'right.wav')
Copy-Item -LiteralPath $Request -Destination (Join-Path $FreshStagingRoot 'request.json')
Copy-Item -LiteralPath $TrainingSnapshot -Destination (Join-Path $FreshStagingRoot 'training-snapshot.json')

$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:PIP_NO_INDEX = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
& $python (Join-Path $PSScriptRoot 'run-remix-musicfm-private-features.py') `
  (Join-Path $FreshStagingRoot 'request.json') `
  (Join-Path $FreshStagingRoot 'training-snapshot.json') `
  --runtime-root $RuntimeRoot `
  --control (Join-Path $inputRoot 'control.wav') `
  --left (Join-Path $inputRoot 'left.wav') `
  --right (Join-Path $inputRoot 'right.wav') `
  --out-dir (Join-Path $FreshStagingRoot 'features')
if ($LASTEXITCODE -ne 0) { throw 'Private MusicFM feature extraction failed.' }
