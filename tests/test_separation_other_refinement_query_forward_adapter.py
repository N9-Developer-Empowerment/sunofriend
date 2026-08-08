from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_forward_math_is_separate_tensor_only_and_single_use() -> None:
    adapter_path = (
        ROOT
        / "src"
        / "sunofriend"
        / "separation_other_refinement_query_forward_adapter.py"
    )
    loading_path = (
        ROOT
        / "src"
        / "sunofriend"
        / "separation_other_refinement_query_model_loading.py"
    )
    adapter = adapter_path.read_text(encoding="utf-8")
    loading = loading_path.read_text(encoding="utf-8")

    assert "class SingleUseBanquetForward" in adapter
    assert "def run_once(" in adapter
    assert "has already been attempted" in adapter
    assert "argparse" not in adapter
    assert "Path(" not in adapter
    assert "torch.load" not in adapter
    assert "socket" not in adapter
    assert "soundfile" not in adapter
    assert "torchaudio.load" not in adapter
    assert ".open(" not in adapter
    assert "def forward" not in loading


def test_runner_contains_exactly_one_single_use_forward_call_and_no_audio_path() -> None:
    runner_path = (
        ROOT / "scripts" / "run-separation-other-refinement-query-synthetic.py"
    )
    source = runner_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run_once"
    ]

    assert len(calls) == 1
    assert 'parser.add_argument("--audio"' not in source
    assert "soundfile" not in source
    assert "librosa" not in source
    assert "public_activation\": False" not in source  # projected centrally
    assert "source_selection\": False" not in source
    assert "midi_created\": False" not in source
    assert "--accept-approved-synthetic-forward" in source
    assert "SingleUseBanquetForward" in source


def test_forward_adapter_tracks_the_pinned_upstream_operation_order() -> None:
    source = (
        ROOT
        / "src"
        / "sunofriend"
        / "separation_other_refinement_query_forward_adapter.py"
    ).read_text(encoding="utf-8")
    ordered = [
        "mixture_spectrogram = model.stft(mixture)",
        "encoded = _band_split(model, mixture_spectrogram)",
        "encoded = _time_frequency_model(model, encoded)",
        "query_embedding = _query_embedding(model, query)",
        "conditioned = _condition(model, encoded, query_embedding)",
        "mask = _estimate_mask(model, conditioned)",
        "target_spectrogram = mixture_spectrogram * mask",
        "return model.istft",
    ]
    positions = [source.index(fragment) for fragment in ordered]

    assert positions == sorted(positions)
    assert "value = gamma * value" in source
    assert "value = value + beta" in source
    assert "get_buffer(f\"freq_weights/{index}\")" in source
