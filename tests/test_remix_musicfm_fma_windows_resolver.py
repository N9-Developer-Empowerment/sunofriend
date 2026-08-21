from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve-remix-musicfm-fma-runtime-windows.ps1"


def test_native_windows_resolver_is_metadata_only_and_uses_native_markers() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'if (-not $IsWindows)' in source
    assert '"--dry-run"' in source
    assert '"--ignore-installed"' in source
    assert '"--report", $Report' in source
    assert '"--only-binary=:all:"' in source
    assert "--platform" not in source
    assert "--target" not in source
    assert "pip download" not in source
    assert '"torch==2.7.1+cu128"' in source
    assert '"torchaudio==2.7.1+cu128"' in source
    assert '"transformers==4.53.2"' in source
    assert '"einops==0.8.1"' in source
    assert 'wheel_files_retained = $false' in source
    assert 'packages_installed = $false' in source
    assert 'model_loaded = $false' in source
    assert 'training_started = $false' in source


def test_native_windows_resolver_refuses_overwrite_and_retains_report_identity() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "OutputDirectory must be a fresh path" in source
    assert 'Get-FileHash -LiteralPath $Report -Algorithm SHA256' in source
    assert 'filename = "native-windows-pip-report.json"' in source
    assert 'status = "metadata_only_resolution_complete_unvalidated"' in source
