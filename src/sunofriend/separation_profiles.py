"""Immutable public profile registry for local finished-mix separation.

Profiles describe exact software, model and policy identities.  Installation
state is deliberately separate: registering a profile never downloads or
loads it, and a blocked profile remains visible without becoming executable.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


PROFILE_REGISTRY_SCHEMA = "sunofriend.separation-profile-registry.v1"
PROFILE_STATUSES = ("blocked", "public_opt_in", "studio_challenger", "retired")

KIM_VOCAL_PROFILE_ID = "kim-vocal-2-mlx-v1"
CORE_FOUR_PROFILE_ID = "demucs-mlx-htdemucs-v1"
CORE_FOUR_FALLBACK_PROFILE_ID = "demucs-infer-htdemucs-fallback-v1"
SCNET_CANDIDATE_PROFILE_ID = "scnet-large-musdb-candidate-v1"
SCNET_RELEASE_PROFILE_ID = "scnet-large-musdb-release-v1"
DEMUCS_INFER_CHALLENGER_ID = "demucs-infer-htdemucs-studio-v1"
OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID = (
    "demucs-mlx-htdemucs-6s-other-refinement-v1"
)


@dataclass(frozen=True)
class ArtifactIdentity:
    name: str
    relative_path: str
    sha256: str
    bytes: int
    source_url: str
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "source_url": self.source_url,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class PackageIdentity:
    name: str
    version: str
    inference_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "inference_required": self.inference_required,
        }


@dataclass(frozen=True)
class SeparationProfileSpec:
    profile_id: str
    scope_id: str
    backend: str
    status: str
    target_release_tier: str
    selection_priority: int
    model_id: str
    model_revision: str
    runtime_source_revision: str
    runtime_wheel_sha256: str | None
    runtime_identity: tuple[PackageIdentity, ...]
    artifacts: tuple[ArtifactIdentity, ...]
    supported_roles: tuple[str, ...]
    terms_evidence: tuple[str, ...]
    known_limitations: tuple[str, ...]
    blockers: tuple[str, ...]
    setup_script: str
    worker_script: str
    inference_settings: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        if self.status not in PROFILE_STATUSES:
            raise ValueError(f"unsupported separation profile status: {self.status}")
        if not self.profile_id or not self.supported_roles:
            raise ValueError("profile identity and supported roles are required")
        if len(set(self.supported_roles)) != len(self.supported_roles):
            raise ValueError("profile supported roles must be unique")

    @property
    def executable(self) -> bool:
        return self.status in {"public_opt_in", "studio_challenger"}

    def packages(self) -> Mapping[str, str]:
        return MappingProxyType(
            {item.name: item.version for item in self.runtime_identity}
        )

    def artifact(self, name: str) -> ArtifactIdentity:
        for item in self.artifacts:
            if item.name == name:
                return item
        raise KeyError(f"profile {self.profile_id!r} has no artifact {name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "scope_id": self.scope_id,
            "backend": self.backend,
            "status": self.status,
            "target_release_tier": self.target_release_tier,
            "selection_priority": self.selection_priority,
            "executable": self.executable,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "runtime_source_revision": self.runtime_source_revision,
            "runtime_wheel_sha256": self.runtime_wheel_sha256,
            "runtime_identity": [item.to_dict() for item in self.runtime_identity],
            "artifacts": [item.to_dict() for item in self.artifacts],
            "supported_roles": list(self.supported_roles),
            "terms_evidence": list(self.terms_evidence),
            "known_limitations": list(self.known_limitations),
            "blockers": list(self.blockers),
            "setup_script": self.setup_script,
            "worker_script": self.worker_script,
            "inference_settings": dict(self.inference_settings),
        }


_CORE_MODEL_BASE = (
    "https://huggingface.co/mlx-community/demucs-mlx/resolve/"
    "d4519e24ddc2dd4a11d56a193092433d852c3961"
)
_CORE_RUNTIME_BASE = (
    "https://raw.githubusercontent.com/ssmall256/demucs-mlx/"
    "b37e6ba3c5985af531f61c43564cf13c6ed349fd"
)

_PROFILES: Mapping[str, SeparationProfileSpec] = MappingProxyType(
    {
        KIM_VOCAL_PROFILE_ID: SeparationProfileSpec(
            profile_id=KIM_VOCAL_PROFILE_ID,
            scope_id="broad-vocals-v1",
            backend="mlx-audio-mel-roformer",
            status="public_opt_in",
            target_release_tier="public_opt_in",
            selection_priority=10,
            model_id="mlx-community/mel-roformer-kim-vocal-2-mlx",
            model_revision="64cbfcb004e39430e5f584552c05949440ec39ce",
            runtime_source_revision="41092c02db18efd5b9d8281b2fcc41d84801757a",
            runtime_wheel_sha256=None,
            runtime_identity=(
                PackageIdentity("mlx", "0.31.2"),
                PackageIdentity("mlx-metal", "0.31.2"),
                PackageIdentity("numpy", "2.3.5"),
            ),
            artifacts=(
                ArtifactIdentity(
                    name="weights",
                    relative_path="model.safetensors",
                    sha256="312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5",
                    bytes=456_483_463,
                    source_url=(
                        "https://huggingface.co/mlx-community/"
                        "mel-roformer-kim-vocal-2-mlx/resolve/"
                        "64cbfcb004e39430e5f584552c05949440ec39ce/"
                        "model.safetensors"
                    ),
                    purpose="broad-vocal MLX checkpoint",
                ),
            ),
            supported_roles=("vocals", "instrumental"),
            terms_evidence=(
                "Pinned model repository LICENSE and model card retained by setup.",
                "Pinned MLX Audio source LICENSE retained by setup.",
            ),
            known_limitations=(
                "Produces broad vocals and complementary instrumental only.",
                "Outputs are unreviewed estimates and can contain bleed or artefacts.",
            ),
            blockers=(),
            setup_script="scripts/setup-separation-alpha-macos.sh",
            worker_script="src/sunofriend/separation_worker.py",
            inference_settings=(("device", "mlx-gpu"),),
        ),
        CORE_FOUR_PROFILE_ID: SeparationProfileSpec(
            profile_id=CORE_FOUR_PROFILE_ID,
            scope_id="core-four-stems-v1",
            backend="demucs-mlx",
            status="blocked",
            target_release_tier="public_opt_in",
            selection_priority=10,
            model_id="mlx-community/demucs-mlx:htdemucs",
            model_revision="d4519e24ddc2dd4a11d56a193092433d852c3961",
            runtime_source_revision="b37e6ba3c5985af531f61c43564cf13c6ed349fd",
            runtime_wheel_sha256="dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64",
            runtime_identity=(
                PackageIdentity("demucs-mlx", "1.4.4"),
                PackageIdentity("mlx", "0.31.2"),
                PackageIdentity("mlx-metal", "0.31.2"),
                PackageIdentity("mlx-audio-io", "1.3.11"),
                PackageIdentity("mlx-spectro", "0.7.0"),
                PackageIdentity("numpy", "2.3.5"),
                PackageIdentity("packaging", "25.0"),
                PackageIdentity("tqdm", "4.67.1"),
                PackageIdentity("safetensors", "0.6.2"),
            ),
            artifacts=(
                ArtifactIdentity(
                    name="weights",
                    relative_path="model/htdemucs.safetensors",
                    sha256="339d267a7a6983a11eedbdc00413c602a65e9b9103f695fb5c2b2a481cd9d297",
                    bytes=168_005_865,
                    source_url=f"{_CORE_MODEL_BASE}/htdemucs.safetensors",
                    purpose="pre-converted MLX weights",
                ),
                ArtifactIdentity(
                    name="config",
                    relative_path="model/htdemucs_config.json",
                    sha256="9258499513944fc062fbca0f11be425a446ec5702869a87e225323d7a57d2a01",
                    bytes=1_892,
                    source_url=f"{_CORE_MODEL_BASE}/htdemucs_config.json",
                    purpose="exact model construction and four-role mapping",
                ),
                ArtifactIdentity(
                    name="model_card",
                    relative_path="TERMS/model-README.md",
                    sha256="1f9e7231385b9a8356dbe443c9707e9ada483027277ef0fd4154143f516570ab",
                    bytes=3_971,
                    source_url=f"{_CORE_MODEL_BASE}/README.md",
                    purpose="model provenance and MIT metadata evidence",
                ),
                ArtifactIdentity(
                    name="runtime_license",
                    relative_path="TERMS/demucs-mlx-LICENSE",
                    sha256="15086279d32c0f00c577c0f52ff428daf98b8a1fec0264da1c717c88ad464f51",
                    bytes=1_117,
                    source_url=f"{_CORE_RUNTIME_BASE}/LICENSE",
                    purpose="pinned runtime MIT terms evidence",
                ),
                ArtifactIdentity(
                    name="runtime_pyproject",
                    relative_path="TERMS/demucs-mlx-pyproject.toml",
                    sha256="3758e87bc8b8d2755e27c764fc7c464def17cd6e2ccef58817689524534ffe36",
                    bytes=1_672,
                    source_url=f"{_CORE_RUNTIME_BASE}/pyproject.toml",
                    purpose="pinned source dependency and provenance evidence",
                ),
            ),
            supported_roles=("vocals", "drums", "bass", "other"),
            terms_evidence=(
                "The pinned demucs-mlx source revision declares MIT terms.",
                "The pinned MLX Community model card declares MIT metadata and direct original-checkpoint conversion provenance.",
                "Artifact SHA-256 identities and source revisions are immutable profile inputs.",
            ),
            known_limitations=(
                "Other is a grouped remainder, not separate guitar, piano or keys.",
                "The persisted other includes an explicit reconstruction correction.",
                "Good reconstruction proves accounting, not separation accuracy.",
                "Musical usefulness varies by recording and always needs listening.",
                "The first verified resource class is a 16 GiB Apple-silicon Mac; other Apple-silicon classes are accessible but unverified.",
                "The pinned config encodes segment as the fraction string 39/5; the runtime repeats that string while calculating HTDemucs training length.",
            ),
            blockers=(
                "Objective activation failed for the baseline and its single permitted remediation; further demucs-mlx retries are disabled.",
                "Public core-four work must switch to a separately pinned, approved and objectively qualified fallback backend.",
            ),
            setup_script="scripts/setup-separation-core-four-macos.sh",
            worker_script="src/sunofriend/separation_demucs_mlx_worker.py",
            inference_settings=(
                ("model", "htdemucs"),
                ("shifts", 1),
                ("seed", 0),
                ("overlap", 0.25),
                ("batch_size", 1),
                ("writer_count", 1),
                ("segment_seconds", 7.8),
                ("segment_source", "pinned_config_fraction_39_over_5"),
                ("auto_convert", False),
            ),
        ),
        CORE_FOUR_FALLBACK_PROFILE_ID: SeparationProfileSpec(
            profile_id=CORE_FOUR_FALLBACK_PROFILE_ID,
            scope_id="core-four-stems-v1",
            backend="demucs-infer",
            status="blocked",
            target_release_tier="public_opt_in",
            selection_priority=20,
            model_id="htdemucs:955717e8",
            model_revision="955717e8-8726e21a",
            runtime_source_revision="4b79d5c756ce298503d90b0cca2abbc76c565416",
            runtime_wheel_sha256="df07b115690021dcfa6b2a6de1b7b352741111bc46fad31ca83eaaba6afced8b",
            runtime_identity=(
                PackageIdentity("cffi", "2.1.1"),
                PackageIdentity("demucs-infer", "4.2.2"),
                PackageIdentity("einops", "0.8.2"),
                PackageIdentity("filelock", "3.32.2"),
                PackageIdentity("fsspec", "2026.7.0"),
                PackageIdentity("Jinja2", "3.1.6"),
                PackageIdentity("julius", "0.2.8"),
                PackageIdentity("MarkupSafe", "3.0.3"),
                PackageIdentity("mpmath", "1.3.0"),
                PackageIdentity("networkx", "3.6.1"),
                PackageIdentity("numpy", "2.5.1"),
                PackageIdentity("pycparser", "3.0"),
                PackageIdentity("PyYAML", "6.0.3"),
                PackageIdentity("setuptools", "83.0.0"),
                PackageIdentity("soundfile", "0.14.0"),
                PackageIdentity("sympy", "1.14.0"),
                PackageIdentity("torch", "2.8.0"),
                PackageIdentity("torchaudio", "2.8.0"),
                PackageIdentity("tqdm", "4.70.0"),
                PackageIdentity("typing-extensions", "4.16.0"),
            ),
            artifacts=(
                ArtifactIdentity(
                    name="weights",
                    relative_path="model/955717e8-8726e21a.th",
                    sha256="8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4",
                    bytes=84_141_911,
                    source_url="https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th",
                    purpose="single official htdemucs checkpoint",
                ),
                ArtifactIdentity(
                    name="config",
                    relative_path="model/htdemucs.yaml",
                    sha256="239c445d0b14454d541ad8bd9bb271c9e536d267e8a4625208744cbb2e7bb66c",
                    bytes=21,
                    source_url="https://raw.githubusercontent.com/openmirlab/demucs-infer/4b79d5c756ce298503d90b0cca2abbc76c565416/demucs_infer/remote/htdemucs.yaml",
                    purpose="single-model local repository binding",
                ),
                ArtifactIdentity(
                    name="runtime_license",
                    relative_path="TERMS/demucs-infer-LICENSE",
                    sha256="761f67137c6e733d551b8ed1111e48e267e032c2c0fb0df07127cf55ddbeef5b",
                    bytes=1_400,
                    source_url="https://raw.githubusercontent.com/openmirlab/demucs-infer/4b79d5c756ce298503d90b0cca2abbc76c565416/LICENSE",
                    purpose="pinned runtime MIT terms evidence",
                ),
                ArtifactIdentity(
                    name="model_card",
                    relative_path="TERMS/demucs-infer-README.md",
                    sha256="ace60d8646c7b74e6f631a4ed635ba9a2894e48e24490df0501e2e6b51cfd0a4",
                    bytes=23_660,
                    source_url="https://raw.githubusercontent.com/openmirlab/demucs-infer/4b79d5c756ce298503d90b0cca2abbc76c565416/README.md",
                    purpose="model provenance and repository MIT metadata",
                ),
                ArtifactIdentity(
                    name="runtime_pyproject",
                    relative_path="TERMS/demucs-infer-pyproject.toml",
                    sha256="ad3e58df8469056f030cddc00f61be64dcffcaec3a3dcd03da2f100fde154aa8",
                    bytes=3_560,
                    source_url="https://raw.githubusercontent.com/openmirlab/demucs-infer/4b79d5c756ce298503d90b0cca2abbc76c565416/pyproject.toml",
                    purpose="pinned runtime dependency and provenance evidence",
                ),
                ArtifactIdentity(
                    name="checkpoint_provenance",
                    relative_path="TERMS/checkpoints-provenance.json",
                    sha256="e209056d816cdc8f91be9cfdf9c1883aec9e34f739fc4278de2ebb60d58e5b75",
                    bytes=7_467,
                    source_url="https://raw.githubusercontent.com/openmirlab/demucs-infer/4b79d5c756ce298503d90b0cca2abbc76c565416/docs/checkpoints_provenance.json",
                    purpose="full checkpoint SHA-256 provenance evidence",
                ),
            ),
            supported_roles=("vocals", "drums", "bass", "other"),
            terms_evidence=(
                "The pinned demucs-infer repository declares MIT and identifies the model weights as unchanged original Demucs artifacts.",
                "The pinned provenance document binds the checkpoint URL and full SHA-256.",
                "No separate checkpoint licence file was located and no contradictory use restriction was found; this limitation is disclosed for approval.",
            ),
            known_limitations=(
                "Other is a grouped remainder, not separate guitar, piano or keys.",
                "The persisted other includes an explicit reconstruction correction.",
                "Good reconstruction proves accounting, not separation accuracy.",
                "This fallback uses native Apple-arm64 PyTorch on CPU; performance on the 16 GiB class is unverified.",
                "The original checkpoint has no separate model-specific licence file.",
                "The installed model exposes its native segment as Fraction(39, 5), which the pinned worker contract rejects before inference.",
            ),
            blockers=(
                "The revised install passed exact receipt and doctor checks, but the synthetic worker failed before publication on the native Fraction segment contract.",
                "The one fallback remediation is exhausted; new installs and activation retries are disabled.",
                "Public core-four work requires a separately reviewed, pinned and objectively qualified backend.",
            ),
            setup_script="scripts/setup-separation-core-four-fallback-macos.sh",
            worker_script="src/sunofriend/separation_demucs_infer_worker.py",
            inference_settings=(
                ("model", "htdemucs"),
                ("signature", "955717e8"),
                ("shifts", 1),
                ("seed", 0),
                ("overlap", 0.25),
                ("batch_size", 1),
                ("writer_count", 1),
                ("segment", "native_fraction_39_over_5_rejected"),
                ("device", "cpu"),
                ("explicit_local_repo", True),
            ),
        ),
        SCNET_CANDIDATE_PROFILE_ID: SeparationProfileSpec(
            profile_id=SCNET_CANDIDATE_PROFILE_ID,
            scope_id="core-four-stems-v1",
            backend="scnet-official-source-adapter",
            status="blocked",
            target_release_tier="public_opt_in",
            selection_priority=0,
            model_id="official SCNet-large MUSDB checkpoint",
            model_revision=(
                "google-drive:1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t:"
                "sha256:719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
            ),
            runtime_source_revision=(
                "5d95bf96b19c3eede63248d171efeca8e3abb948"
            ),
            runtime_wheel_sha256=None,
            runtime_identity=(
                PackageIdentity("filelock", "3.32.2"),
                PackageIdentity("fsspec", "2026.7.0"),
                PackageIdentity("Jinja2", "3.1.6"),
                PackageIdentity("MarkupSafe", "3.0.3"),
                PackageIdentity("mpmath", "1.3.0"),
                PackageIdentity("networkx", "3.6.1"),
                PackageIdentity("numpy", "2.5.1"),
                PackageIdentity("PyYAML", "6.0.3"),
                PackageIdentity("setuptools", "83.0.0"),
                PackageIdentity("sympy", "1.14.0"),
                PackageIdentity("torch", "2.8.0"),
                PackageIdentity("typing-extensions", "4.16.0"),
            ),
            artifacts=(
                ArtifactIdentity(
                    name="weights",
                    relative_path="model/SCNet-large.th",
                    sha256=(
                        "719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
                    ),
                    bytes=168_848_417,
                    source_url=(
                        "https://drive.google.com/file/d/"
                        "1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t/view"
                    ),
                    purpose="official README-linked SCNet-large checkpoint",
                ),
                ArtifactIdentity(
                    name="config",
                    relative_path="model/scnet-large-config.yaml",
                    sha256=(
                        "629a4901184bf1d3a75b0b13904f35974785aa042cad3c010fd576248cdce3f0"
                    ),
                    bytes=1_080,
                    source_url=(
                        "https://drive.google.com/file/d/"
                        "1qxK7SZx6-Gsp1s3wCrj98X7--UcI4O3K/view"
                    ),
                    purpose="official linked SCNet-large four-role config",
                ),
                ArtifactIdentity(
                    name="source_license",
                    relative_path="TERMS/SCNet-LICENSE",
                    sha256=(
                        "0bdf1b69335198118ab16cfc50d337b496b8c6d90e83beeaba4643781ab62513"
                    ),
                    bytes=1_067,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "5d95bf96b19c3eede63248d171efeca8e3abb948/LICENSE"
                    ),
                    purpose="pinned official source MIT terms evidence",
                ),
                ArtifactIdentity(
                    name="source_readme",
                    relative_path="TERMS/SCNet-README.md",
                    sha256=(
                        "edc1d7e1f190068eff924b974aa901d5e0b8b560139587787939de04062a009b"
                    ),
                    bytes=2_044,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "5d95bf96b19c3eede63248d171efeca8e3abb948/README.md"
                    ),
                    purpose="official checkpoint-link and provenance evidence",
                ),
                ArtifactIdentity(
                    name="source_requirements",
                    relative_path="TERMS/SCNet-requirements.txt",
                    sha256=(
                        "5af27b6912eddb99793d94936f3ab53e344fb09bd139d75c0969c54086a821bd"
                    ),
                    bytes=136,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "5d95bf96b19c3eede63248d171efeca8e3abb948/requirements.txt"
                    ),
                    purpose="upstream dependency declaration evidence",
                ),
                ArtifactIdentity(
                    name="architecture_source",
                    relative_path="source/scnet/SCNet.py",
                    sha256=(
                        "85a15ea5d28285a0cf0a24d6266a28d043c5a655d47aa41684ef256d84e7bc4a"
                    ),
                    bytes=14_039,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "5d95bf96b19c3eede63248d171efeca8e3abb948/scnet/SCNet.py"
                    ),
                    purpose="exact MIT SCNet architecture source",
                ),
                ArtifactIdentity(
                    name="separation_source",
                    relative_path="source/scnet/separation.py",
                    sha256=(
                        "43402dc6579436d3b5abb921990572684beed8fa10b377a112892b438f40713b"
                    ),
                    bytes=3_783,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "5d95bf96b19c3eede63248d171efeca8e3abb948/scnet/separation.py"
                    ),
                    purpose="exact MIT dual-path separation source",
                ),
            ),
            supported_roles=("vocals", "drums", "bass", "other"),
            terms_evidence=(
                "The pinned official repository source declares MIT.",
                "The pinned official README links SCNet-large and identifies MUSDB training.",
                "The disclosed MIT metadata plus README-linked checkpoint was accepted as sufficient provisional preview evidence on 2026-08-06.",
                "No separate checkpoint terms file or immutable release asset was found.",
            ),
            known_limitations=(
                "The upstream checkpoint remains a mutable Google Drive object; this profile pins the 2026-08-06 observed bytes and SHA-256.",
                "Current source differs from the source at the checkpoint release tag.",
                "Apple-arm64 inference and 16 GiB resource behavior are unverified.",
                "Other is a grouped remainder, not separate guitar, piano or keys.",
            ),
            blockers=(
                "Source/config/checkpoint compatibility has not been proven.",
                "No install script or inference worker is available; separate approval is required before any runtime download, checkpoint load or inference.",
                "Apple-arm64 inference, resource ceilings and reconstruction output remain objectively unqualified.",
            ),
            setup_script="not-available",
            worker_script="not-available",
            inference_settings=(
                ("model", "SCNet-large"),
                ("shifts", 1),
                ("seed", 0),
                ("overlap", 0.25),
                ("segment_seconds", 11),
                ("batch_size", 1),
                ("writer_count", 1),
                ("device", "cpu"),
                ("checkpoint_local_only", True),
            ),
        ),
        SCNET_RELEASE_PROFILE_ID: SeparationProfileSpec(
            profile_id=SCNET_RELEASE_PROFILE_ID,
            scope_id="core-four-stems-v1",
            backend="scnet-official-release-adapter",
            status="public_opt_in",
            target_release_tier="public_opt_in",
            selection_priority=30,
            model_id="official SCNet-large MUSDB checkpoint",
            model_revision=(
                "google-drive:1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t:"
                "sha256:719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
            ),
            runtime_source_revision=(
                "6236f8c559778dc271e1aea9baa3993ae655e905"
            ),
            runtime_wheel_sha256=None,
            runtime_identity=(
                PackageIdentity("filelock", "3.32.2"),
                PackageIdentity("fsspec", "2026.7.0"),
                PackageIdentity("Jinja2", "3.1.6"),
                PackageIdentity("MarkupSafe", "3.0.3"),
                PackageIdentity("mpmath", "1.3.0"),
                PackageIdentity("networkx", "3.6.1"),
                PackageIdentity("numpy", "2.5.1"),
                PackageIdentity("PyYAML", "6.0.3"),
                PackageIdentity("setuptools", "83.0.0"),
                PackageIdentity("sympy", "1.14.0"),
                PackageIdentity("torch", "2.8.0"),
                PackageIdentity("typing-extensions", "4.16.0"),
            ),
            artifacts=(
                ArtifactIdentity(
                    name="weights",
                    relative_path="model/SCNet-large.th",
                    sha256=(
                        "719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070"
                    ),
                    bytes=168_848_417,
                    source_url=(
                        "https://drive.google.com/file/d/"
                        "1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t/view"
                    ),
                    purpose="official README-linked SCNet-large checkpoint",
                ),
                ArtifactIdentity(
                    name="config",
                    relative_path="model/scnet-large-config.yaml",
                    sha256=(
                        "629a4901184bf1d3a75b0b13904f35974785aa042cad3c010fd576248cdce3f0"
                    ),
                    bytes=1_080,
                    source_url=(
                        "https://drive.google.com/file/d/"
                        "1qxK7SZx6-Gsp1s3wCrj98X7--UcI4O3K/view"
                    ),
                    purpose="official linked SCNet-large four-role config",
                ),
                ArtifactIdentity(
                    name="source_license",
                    relative_path="TERMS/SCNet-LICENSE",
                    sha256=(
                        "0bdf1b69335198118ab16cfc50d337b496b8c6d90e83beeaba4643781ab62513"
                    ),
                    bytes=1_067,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "6236f8c559778dc271e1aea9baa3993ae655e905/LICENSE"
                    ),
                    purpose="pinned release-source MIT terms evidence",
                ),
                ArtifactIdentity(
                    name="source_readme",
                    relative_path="TERMS/SCNet-README.md",
                    sha256=(
                        "5216a5b0ae85715f7eedbadda4d8d71dd063fb2bc40ba2a90cb61cf3458136dc"
                    ),
                    bytes=2_031,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "6236f8c559778dc271e1aea9baa3993ae655e905/README.md"
                    ),
                    purpose="release checkpoint-link and provenance evidence",
                ),
                ArtifactIdentity(
                    name="source_requirements",
                    relative_path="TERMS/SCNet-requirements.txt",
                    sha256=(
                        "892a58352a75ee9d6cd98c68de9a4b6c733fb4f2e5788f3c6bd2b07676c2b66f"
                    ),
                    bytes=136,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "6236f8c559778dc271e1aea9baa3993ae655e905/requirements.txt"
                    ),
                    purpose="release dependency declaration evidence",
                ),
                ArtifactIdentity(
                    name="architecture_source",
                    relative_path="source/scnet/SCNet.py",
                    sha256=(
                        "5e77c363f7f0187432a984d8ae1aa511826295d732372f0c280e68e4fecd4550"
                    ),
                    bytes=13_853,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "6236f8c559778dc271e1aea9baa3993ae655e905/scnet/SCNet.py"
                    ),
                    purpose="exact release-tag MIT SCNet architecture source",
                ),
                ArtifactIdentity(
                    name="separation_source",
                    relative_path="source/scnet/separation.py",
                    sha256=(
                        "43402dc6579436d3b5abb921990572684beed8fa10b377a112892b438f40713b"
                    ),
                    bytes=3_783,
                    source_url=(
                        "https://raw.githubusercontent.com/starrytong/SCNet/"
                        "6236f8c559778dc271e1aea9baa3993ae655e905/scnet/separation.py"
                    ),
                    purpose="exact release-tag dual-path separation source",
                ),
            ),
            supported_roles=("vocals", "drums", "bass", "other"),
            terms_evidence=(
                "The pinned official release source declares MIT.",
                "The release README links SCNet-large and identifies MUSDB training.",
                "The disclosed MIT metadata plus README-linked checkpoint was accepted as sufficient provisional preview evidence on 2026-08-06.",
                "No bespoke maintainer permission letter is required for local user-installed preview testing unless later evidence contradicts the pinned terms record.",
                "No separate checkpoint terms file or immutable release asset was found.",
            ),
            known_limitations=(
                "The upstream checkpoint remains a mutable Google Drive object; this profile pins the 2026-08-06 observed bytes and SHA-256.",
                "The release source declares torch 2.0.1 while the exact Apple-arm64 runtime uses torch 2.8.0.",
                "Three same-setting network-denied 60-second synthetic runs passed in 69.97 to 71.18 seconds at 6,581,846,016 to 6,719,586,304-byte peak RSS with byte-identical outputs on the first verified 36 GB M3 Max class; 16 GiB and other Apple-silicon classes remain accessible but unverified.",
                "Three authorised song-disjoint full-song canaries passed offline in 202.91 to 246.65 seconds at 7,457,652,736 to 7,679,950,848-byte peak RSS with zero-LSB reconstruction error; a complete human catastrophic listen reported no corruption, mislabelling, all-role silence or gross timing failure.",
                "On the mathematical fixture, the vocal output was active but extremely quiet and vocal reference energy correlated mainly with grouped other; this is a disclosed usefulness limitation, not an objective preview veto.",
                "Other is a grouped remainder, not separate guitar, piano or keys.",
            ),
            blockers=(),
            setup_script="scripts/setup-separation-core-four-scnet-macos.sh",
            worker_script="src/sunofriend/separation_scnet_worker.py",
            inference_settings=(
                ("model", "SCNet-large"),
                ("shifts", 1),
                ("seed", 0),
                ("overlap", 0.25),
                ("segment_seconds", 11),
                ("batch_size", 1),
                ("writer_count", 1),
                ("device", "cpu"),
                ("checkpoint_local_only", True),
            ),
        ),
        OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID: SeparationProfileSpec(
            profile_id=OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID,
            scope_id="other-refinement-v1",
            backend="demucs-mlx",
            status="studio_challenger",
            target_release_tier="studio_challenger",
            selection_priority=0,
            model_id="mlx-community/demucs-mlx:htdemucs_6s",
            model_revision="d4519e24ddc2dd4a11d56a193092433d852c3961",
            runtime_source_revision=(
                "b37e6ba3c5985af531f61c43564cf13c6ed349fd"
            ),
            runtime_wheel_sha256=(
                "dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64"
            ),
            runtime_identity=(
                PackageIdentity("demucs-mlx", "1.4.4"),
                PackageIdentity("mlx", "0.31.2"),
                PackageIdentity("mlx-metal", "0.31.2"),
                PackageIdentity("mlx-audio-io", "1.3.11"),
                PackageIdentity("mlx-spectro", "0.7.0"),
                PackageIdentity("numpy", "2.3.5"),
                PackageIdentity("packaging", "25.0"),
                PackageIdentity("tqdm", "4.67.1"),
                PackageIdentity("safetensors", "0.6.2"),
            ),
            artifacts=(
                ArtifactIdentity(
                    name="weights",
                    relative_path="model/htdemucs_6s.safetensors",
                    sha256=(
                        "d298f7f746bf53c21baad44fb08e88807ef47feb551dd22f1601a546c85b8e02"
                    ),
                    bytes=109_726_583,
                    source_url=f"{_CORE_MODEL_BASE}/htdemucs_6s.safetensors",
                    purpose="pre-converted six-source MLX weights",
                ),
                ArtifactIdentity(
                    name="config",
                    relative_path="model/htdemucs_6s_config.json",
                    sha256=(
                        "97f8315891d8edc9aa6f59e56e0d352fbad5ebfb8a4faf46341ab2f1844596a9"
                    ),
                    bytes=1_946,
                    source_url=f"{_CORE_MODEL_BASE}/htdemucs_6s_config.json",
                    purpose="exact six-role model construction configuration",
                ),
                ArtifactIdentity(
                    name="model_card",
                    relative_path="TERMS/model-README.md",
                    sha256=(
                        "1f9e7231385b9a8356dbe443c9707e9ada483027277ef0fd4154143f516570ab"
                    ),
                    bytes=3_971,
                    source_url=f"{_CORE_MODEL_BASE}/README.md",
                    purpose="model provenance and MIT metadata evidence",
                ),
                ArtifactIdentity(
                    name="runtime_license",
                    relative_path="TERMS/demucs-mlx-LICENSE",
                    sha256=(
                        "15086279d32c0f00c577c0f52ff428daf98b8a1fec0264da1c717c88ad464f51"
                    ),
                    bytes=1_117,
                    source_url=f"{_CORE_RUNTIME_BASE}/LICENSE",
                    purpose="pinned runtime MIT terms evidence",
                ),
                ArtifactIdentity(
                    name="runtime_pyproject",
                    relative_path="TERMS/demucs-mlx-pyproject.toml",
                    sha256=(
                        "3758e87bc8b8d2755e27c764fc7c464def17cd6e2ccef58817689524534ffe36"
                    ),
                    bytes=1_672,
                    source_url=f"{_CORE_RUNTIME_BASE}/pyproject.toml",
                    purpose="pinned source dependency and provenance evidence",
                ),
            ),
            supported_roles=(
                "drums",
                "bass",
                "other",
                "vocals",
                "guitar",
                "piano",
            ),
            terms_evidence=(
                "The pinned demucs-mlx source revision declares MIT terms.",
                "The pinned MLX Community model card declares MIT metadata and direct original-checkpoint conversion provenance.",
                "The six-source checkpoint, config and model-card identities are bound by exact bytes, SHA-256 and revision.",
                "No bespoke maintainer permission letter is required for a local user-installed Studio experiment unless contradictory evidence appears.",
            ),
            known_limitations=(
                "The official Demucs documentation calls the six-source model experimental and warns that piano has substantial bleed and artefacts.",
                "The keys target is a disclosed piano proxy; it does not claim to isolate synthesizers, organs or every keyboard sound.",
                "Earlier private same-checkpoint evidence found low-energy MLX guitar and piano estimates could diverge from the PyTorch reference.",
                "The pinned config stores segment as the string 39/5; the only allowed first remediation is an exact in-memory Fraction(39, 5) normalization without mutating the artifact.",
                "A six-role model run will persist only the requested guitar or piano-proxy target plus the exact grouped-other residual.",
                "On the first authorised 234-second full-song parent, both guitar and piano-proxy targets were low-energy (RMS 0.00135 and 0.00131); access remains available because this is a musical limitation rather than an objective failure.",
                "The completed fixed five-song, ten-report review found no demonstrated useful guitar extraction: four guitar reports were not useful and the fifth reported severe missing content. The only nominally useful piano-proxy report was a true negative on material without piano, while one piano-like instrument was missed. The profile remains Studio-only and reproducible but is not promoted or selected for MIDI.",
                "The first full-song guitar and keys runs completed offline in 9.94 and 9.22 seconds at 3,492,069,640 and 3,492,069,624-byte peak MLX memory with zero-LSB reconstruction on a 36 GB M3 Max; 16 GiB and other classes remain accessible but unverified.",
            ),
            blockers=(),
            setup_script=(
                "scripts/setup-separation-other-refinement-demucs-mlx-macos.sh"
            ),
            worker_script=(
                "src/sunofriend/"
                "separation_other_refinement_demucs_mlx_worker.py"
            ),
            inference_settings=(
                ("model", "htdemucs_6s"),
                ("model_source_order", "drums,bass,other,vocals,guitar,piano"),
                ("shifts", 1),
                ("seed", 0),
                ("overlap", 0.25),
                ("batch_size", 1),
                ("writer_count", 1),
                ("segment_seconds", 7.8),
                ("segment_source", "pinned_config_fraction_39_over_5"),
                ("auto_convert", False),
                ("device", "mlx-gpu"),
                ("input_role", "other"),
                ("persisted_output_contract", "one_target_plus_exact_residual"),
            ),
        ),
        DEMUCS_INFER_CHALLENGER_ID: SeparationProfileSpec(
            profile_id=DEMUCS_INFER_CHALLENGER_ID,
            scope_id="core-four-stems-v1",
            backend="demucs-infer",
            status="blocked",
            target_release_tier="studio_challenger",
            selection_priority=0,
            model_id="htdemucs challenger not yet pinned",
            model_revision="not-qualified",
            runtime_source_revision="not-qualified",
            runtime_wheel_sha256=None,
            runtime_identity=(),
            artifacts=(),
            supported_roles=("vocals", "drums", "bass", "other"),
            terms_evidence=(),
            known_limitations=(
                "PyTorch is required and Apple-silicon resource behavior has not been qualified.",
                "The upstream package permits network model resolution unless Sunofriend supplies an explicit local repository and denies networking.",
            ),
            blockers=(
                "Static fallback audit is incomplete until every Apple-arm64 runtime dependency and artifact is hash-pinned.",
                "Install and execution require a new reviewed plan and separate explicit approval.",
                "Studio comparison remains unavailable until two named profiles are already installed and objectively qualified.",
            ),
            setup_script="not-available",
            worker_script="not-available",
            inference_settings=(),
        ),
    }
)


def separation_profile(profile_id: str) -> SeparationProfileSpec:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        available = ", ".join(sorted(_PROFILES))
        raise ValueError(
            f"unknown separation profile {profile_id!r}; choose one of: {available}"
        ) from exc


def profile_for_scope(scope_id: str) -> SeparationProfileSpec:
    candidates = [item for item in _PROFILES.values() if item.scope_id == scope_id]
    public = [item for item in candidates if item.target_release_tier == "public_opt_in"]
    if not public:
        raise RuntimeError(f"scope {scope_id!r} has no public baseline profile")
    highest = max(item.selection_priority for item in public)
    selected = [item for item in public if item.selection_priority == highest]
    if len(selected) != 1:
        raise RuntimeError(f"scope {scope_id!r} has no unique selected public profile")
    return selected[0]


def separation_profile_registry() -> dict[str, Any]:
    return {
        "schema": PROFILE_REGISTRY_SCHEMA,
        "profiles": [item.to_dict() for item in _PROFILES.values()],
        "policy": {
            "profile_records_are_immutable": True,
            "registration_installs_or_loads_nothing": True,
            "preview_admission_uses_objective_gates_only": True,
            "subjective_feedback_blocks_preview": False,
            "automatic_model_promotion": False,
            "automatic_model_selection": False,
            "challengers_are_studio_only": True,
        },
    }


__all__ = [
    "ArtifactIdentity",
    "CORE_FOUR_PROFILE_ID",
    "CORE_FOUR_FALLBACK_PROFILE_ID",
    "DEMUCS_INFER_CHALLENGER_ID",
    "KIM_VOCAL_PROFILE_ID",
    "OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID",
    "PROFILE_REGISTRY_SCHEMA",
    "PROFILE_STATUSES",
    "PackageIdentity",
    "SCNET_CANDIDATE_PROFILE_ID",
    "SCNET_RELEASE_PROFILE_ID",
    "SeparationProfileSpec",
    "profile_for_scope",
    "separation_profile",
    "separation_profile_registry",
]
