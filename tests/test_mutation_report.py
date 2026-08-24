from __future__ import annotations

import json
from pathlib import Path

import pytest

from devtools.architecture_viewer.analyzer import analyse_source_tree
from devtools.architecture_viewer.overlays import build_overlay_bundle
from devtools.mutation_report import (
    build_mutation_report,
    serialize_report,
    write_fresh_report,
)


def _fixture(repository: Path) -> tuple[dict[str, object], Path, Path]:
    package = repository / "src" / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "logic.py").write_text(
        """def choose(flag: bool) -> int:
    if flag:
        return 1
    return 0

class API:
    def run(self) -> int:
        return choose(True)
""",
        encoding="utf-8",
    )
    architecture = analyse_source_tree(package, repository_root=repository)
    mutants_root = repository / "mutants"
    metadata = mutants_root / "src" / "sample" / "logic.py.meta"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        json.dumps(
            {
                "exit_code_by_key": {
                    "sample.logic.x_choose__mutmut_1": 1,
                    "sample.logic.x_choose__mutmut_2": 0,
                    "sample.logic.x\u01c1API\u01c1run__mutmut_1": 36,
                }
            }
        ),
        encoding="utf-8",
    )
    classifications = repository / "classifications.json"
    classifications.write_text(
        json.dumps(
            {
                "schema": "sunofriend-mutation-classifications.v1",
                "default_survivor": {
                    "classification": "test_gap",
                    "rationale": "not distinguished",
                },
                "rules": [],
            }
        ),
        encoding="utf-8",
    )
    return architecture, mutants_root, classifications


def test_report_is_source_bound_classified_and_deterministic(tmp_path: Path) -> None:
    architecture, mutants_root, classifications = _fixture(tmp_path)

    report = build_mutation_report(
        architecture=architecture,
        mutants_root=mutants_root,
        classifications_path=classifications,
        source_tree_sha256_before=architecture["source_tree_sha256"],
        mutmut_version="3.fixture",
    )
    repeated = build_mutation_report(
        architecture=architecture,
        mutants_root=mutants_root,
        classifications_path=classifications,
        source_tree_sha256_before=architecture["source_tree_sha256"],
        mutmut_version="3.fixture",
    )

    assert report["run_status"] == "advisory_complete"
    assert report["summary"] == {
        "mutant_count": 3,
        "status_counts": {"killed": 1, "survived": 1, "timeout": 1},
        "survivor_classifications": {"test_gap": 1},
    }
    assert serialize_report(report) == serialize_report(repeated)
    records = {record["id"]: record for record in report["mutants"]}
    survivor = records["sample.logic.x_choose__mutmut_2"]
    assert survivor["target"]["qualified_name"] == "choose"
    assert survivor["equivalence"]["classification"] == "test_gap"
    method = records["sample.logic.x\u01c1API\u01c1run__mutmut_1"]
    assert method["target"]["qualified_name"] == "API.run"
    assert method["status"] == "timeout"

    output = tmp_path / "quality" / "mutation.json"
    write_fresh_report(output, report)
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError, match="already exists"):
        write_fresh_report(output, report)


def test_report_attaches_to_current_architecture(tmp_path: Path) -> None:
    architecture, mutants_root, classifications = _fixture(tmp_path)
    report = build_mutation_report(
        architecture=architecture,
        mutants_root=mutants_root,
        classifications_path=classifications,
        source_tree_sha256_before=architecture["source_tree_sha256"],
        mutmut_version="3.fixture",
    )
    report_path = tmp_path / "mutation.json"
    report_path.write_bytes(serialize_report(report))

    bundle = build_overlay_bundle(architecture, mutation_report=report_path)

    records = bundle["documents"][0]["records"]
    assert len(records) == 3
    assert {record["attachment"] for record in records} == {"current"}


def test_report_rejects_stale_source_and_unknown_results(tmp_path: Path) -> None:
    architecture, mutants_root, classifications = _fixture(tmp_path)
    with pytest.raises(ValueError, match="source tree changed"):
        build_mutation_report(
            architecture=architecture,
            mutants_root=mutants_root,
            classifications_path=classifications,
            source_tree_sha256_before="0" * 64,
            mutmut_version="3.fixture",
        )

    metadata = mutants_root / "src" / "sample" / "logic.py.meta"
    document = json.loads(metadata.read_text(encoding="utf-8"))
    document["exit_code_by_key"]["sample.logic.x_choose__mutmut_1"] = 999
    metadata.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported mutmut exit code"):
        build_mutation_report(
            architecture=architecture,
            mutants_root=mutants_root,
            classifications_path=classifications,
            source_tree_sha256_before=architecture["source_tree_sha256"],
            mutmut_version="3.fixture",
        )
