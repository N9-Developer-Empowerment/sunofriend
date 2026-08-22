#!/usr/bin/env python3
"""Create a fresh synthetic frozen-feature remix-ranker request package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from sunofriend.remix_ranker_training import (
    build_synthetic_remix_training_snapshot,
    create_remix_frozen_feature_manifest,
    create_remix_ranker_training_request,
    synthetic_frozen_values,
    write_frozen_feature_vector,
)
from sunofriend.source_receipt import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument(
        "--dependency-contract",
        type=Path,
        required=True,
        help="exact existing dependency/runtime contract whose bytes are bound",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != args.repository_commit:
        raise SystemExit("repository HEAD differs from --repository-commit")
    dependency = args.dependency_contract.resolve()
    if dependency.is_symlink() or not dependency.is_file():
        raise SystemExit("dependency contract must be an existing non-symlink file")
    output = args.out_dir
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    features = output / "features"
    features.mkdir(mode=0o700)
    snapshot = build_synthetic_remix_training_snapshot()
    rows = []
    for index, (variant_hash, values) in enumerate(
        sorted(synthetic_frozen_values().items()), start=1
    ):
        artifact = write_frozen_feature_vector(
            features / f"feature-{index:03d}.json",
            variant_evidence_sha256=variant_hash,
            values=values,
        )
        rows.append(
            {
                "variant_evidence_sha256": variant_hash,
                "artifact": artifact,
                "shape": [len(values)],
                "dtype": "float64-json-number",
                "finite": True,
            }
        )
    extractor = {
        "name": "synthetic-frozen-vector-v1",
        "source_revision": args.repository_commit,
        "checkpoint_sha256": "0" * 64,
        "license_spdx": "CC0-1.0",
        "layer": "fixture",
        "sample_rate_hz": 24_000,
        "feature_rate_hz": 25.0,
        "pooling": "synthetic_fixed_vector",
        "feature_dimension": 8,
        "dtype": "float64-json-number",
        "extractor_frozen": True,
        "gradient_into_extractor": False,
    }
    manifest = create_remix_frozen_feature_manifest(
        snapshot,
        feature_root=features,
        rows=rows,
        feature_set_id="synthetic-frozen-remix-fixture-001",
        repository_commit=args.repository_commit,
        extractor=extractor,
        synthetic_only=True,
    )
    dependency_sha256 = hashlib.sha256(dependency.read_bytes()).hexdigest()
    request = create_remix_ranker_training_request(
        snapshot,
        manifest,
        feature_root=features,
        request_id="synthetic-remix-ranker-request-001",
        repository_commit=args.repository_commit,
        dependency_contract_sha256=dependency_sha256,
    )
    for name, document in (
        ("snapshot.json", snapshot),
        ("feature-manifest.json", manifest),
        ("request.json", request),
    ):
        path = output / name
        with path.open("xb") as handle:
            handle.write(canonical_json_bytes(document))
        path.chmod(0o600)
    print(
        json.dumps(
            {
                "output": str(output),
                "request_sha256": request["document_sha256"],
                "synthetic_only": True,
                "real_training_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
