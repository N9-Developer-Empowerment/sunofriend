param(
    [Parameter(Mandatory = $true)]
    [string]$Python,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $IsWindows) {
    throw "This metadata-only resolver must run natively on Windows."
}

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "OutputDirectory must be a fresh path."
}

$Version = (& $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if ($LASTEXITCODE -ne 0 -or -not $Version.StartsWith("3.11.")) {
    throw "The resolver requires an existing CPython 3.11 interpreter."
}

$Output = New-Item -ItemType Directory -Path $OutputDirectory
$Report = Join-Path $Output.FullName "native-windows-pip-report.json"
$Log = Join-Path $Output.FullName "native-windows-pip-output.txt"
$Receipt = Join-Path $Output.FullName "native-windows-resolution-receipt.json"

$env:PIP_NO_CACHE_DIR = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_PROGRESS_BAR = "off"

$Arguments = @(
    "-m", "pip", "install",
    "--dry-run",
    "--ignore-installed",
    "--report", $Report,
    "--only-binary=:all:",
    "--index-url", "https://download.pytorch.org/whl/cu128",
    "--extra-index-url", "https://pypi.org/simple",
    "torch==2.7.1+cu128",
    "torchaudio==2.7.1+cu128",
    "transformers==4.53.2",
    "einops==0.8.1"
)

& $Python @Arguments 2>&1 | Tee-Object -FilePath $Log
if ($LASTEXITCODE -ne 0) {
    throw "Native Windows metadata-only dependency resolution failed."
}

if (-not (Test-Path -LiteralPath $Report -PathType Leaf)) {
    throw "pip did not create its resolver report."
}

$ReportItem = Get-Item -LiteralPath $Report
$ReportHash = (Get-FileHash -LiteralPath $Report -Algorithm SHA256).Hash.ToLowerInvariant()
$ReceiptDocument = [ordered]@{
    schema = "sunofriend.remix-musicfm-fma-native-windows-resolution-receipt.v0"
    status = "metadata_only_resolution_complete_unvalidated"
    platform = [ordered]@{
        operating_system = "Windows"
        architecture = $env:PROCESSOR_ARCHITECTURE
        python_version = $Version
    }
    report = [ordered]@{
        filename = "native-windows-pip-report.json"
        bytes = $ReportItem.Length
        sha256 = $ReportHash
    }
    resolver_policy = [ordered]@{
        native_environment_markers = $true
        ignore_installed = $true
        only_binary = $true
        pip_cache_disabled = $true
        wheel_files_retained = $false
        packages_installed = $false
        packages_imported = $false
        model_loaded = $false
        audio_opened = $false
        inference_run = $false
        training_started = $false
    }
    authority = [ordered]@{
        dependency_download_authorized = $false
        dependency_install_authorized = $false
        model_import_authorized = $false
        model_load_authorized = $false
        inference_authorized = $false
        private_audio_access_authorized = $false
        training_execution_authorized = $false
        product_ordering_changed = $false
    }
}

$ReceiptDocument | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Receipt -Encoding utf8
Write-Output $Report
Write-Output $Receipt
