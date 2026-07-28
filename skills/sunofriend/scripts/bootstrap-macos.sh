#!/usr/bin/env bash
#
# Conservative first-run installer for a Sunofriend skill on macOS.
#
# The default action is inspection only. A separately confirmed --prepare
# clones the source without installing it. A later --apply must name the exact
# reviewed commit and requires a second confirmation.

set -euo pipefail

readonly REPOSITORY_URL="https://github.com/N9-Developer-Empowerment/sunofriend.git"
readonly REPOSITORY_URL_NO_SUFFIX="https://github.com/N9-Developer-Empowerment/sunofriend"
readonly REPOSITORY_BRANCH="main"
readonly SOUNDFONT_URL="https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/684543d5e5efaef08d02be50dcda8d552478fa60/GeneralUser-GS.sf2"
readonly SOUNDFONT_SHA256="9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe"
readonly SOUNDFONT_LICENSE_URL="https://github.com/mrbumpy409/GeneralUser-GS/blob/684543d5e5efaef08d02be50dcda8d552478fa60/documentation/LICENSE.txt"
readonly SOUNDFONT_RELATIVE_PATH=".local/share/sunofriend/soundfonts/GeneralUser-GS.sf2"

APPLY=0
PREPARE=0
ASSUME_YES=0
EXPECTED_REVISION=""
CHECKOUT_PATH="${HOME}/.local/share/sunofriend/app"
TEMP_CLONE=""
TEMP_SOUNDFONT=""
TEMP_APPROVED_SOURCE=""

usage() {
    cat <<'EOF'
Sunofriend safe macOS bootstrap

Usage:
  bootstrap-macos.sh [--plan]
  bootstrap-macos.sh --prepare [--yes] [--checkout ABSOLUTE_PATH]
  bootstrap-macos.sh --apply --expected-revision 40_HEX_COMMIT [--yes]
      [--checkout ABSOLUTE_PATH]

Modes:
  --plan                 Inspect this Mac and print the exact setup plan.
                         This is the default and makes no changes.
  --prepare              Clone the public source only. It installs no packages
                         or audio assets. Review the exact commit afterwards.
  --apply                Install from the already-prepared checkout. The exact
                         reviewed commit is required and no fetch is performed.
  --yes                  Confirm a previously reviewed prepare/apply action
                         non-interactively. Use only after explicit approval.

Options:
  --checkout PATH        Absolute checkout path. Default:
                         ~/.local/share/sunofriend/app
  --expected-revision    Exact 40-character commit shown by the post-prepare
                         plan. Valid only with --apply.
  -h, --help             Show this help.

Safety:
  * Existing checkouts are inspected but never fetched, pulled or reset.
  * An existing path that is not the expected public repository is rejected.
  * Existing virtual environments and SoundFonts are reused only when valid.
  * A SoundFont with the wrong hash is never replaced automatically.
  * Homebrew itself is never installed by this script.
EOF
}

say() {
    printf '%s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 2
}

cleanup() {
    if [[ -n "${TEMP_CLONE}" && -d "${TEMP_CLONE}" ]]; then
        rm -rf -- "${TEMP_CLONE}"
    fi
    if [[ -n "${TEMP_SOUNDFONT}" && -f "${TEMP_SOUNDFONT}" ]]; then
        rm -f -- "${TEMP_SOUNDFONT}"
    fi
    if [[ -n "${TEMP_APPROVED_SOURCE}" && -d "${TEMP_APPROVED_SOURCE}" ]]; then
        rm -rf -- "${TEMP_APPROVED_SOURCE}"
    fi
}
trap cleanup EXIT INT TERM

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --plan)
                APPLY=0
                PREPARE=0
                shift
                ;;
            --prepare)
                APPLY=0
                PREPARE=1
                shift
                ;;
            --apply)
                APPLY=1
                PREPARE=0
                shift
                ;;
            --yes)
                ASSUME_YES=1
                shift
                ;;
            --checkout)
                [[ $# -ge 2 ]] || die "--checkout requires an absolute path"
                CHECKOUT_PATH="$2"
                shift 2
                ;;
            --expected-revision)
                [[ $# -ge 2 ]] || die "--expected-revision requires a 40-character commit"
                EXPECTED_REVISION="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                die "unknown option: $1 (run with --help)"
                ;;
        esac
    done
    if [[ "${ASSUME_YES}" -eq 1 && "${APPLY}" -ne 1 && "${PREPARE}" -ne 1 ]]; then
        die "--yes is valid only with --prepare or --apply"
    fi
    if [[ -n "${EXPECTED_REVISION}" && "${APPLY}" -ne 1 ]]; then
        die "--expected-revision is valid only with --apply"
    fi
    if [[ "${APPLY}" -eq 1 && -z "${EXPECTED_REVISION}" ]]; then
        die "--apply requires --expected-revision from a reviewed post-prepare plan"
    fi
    if [[ -n "${EXPECTED_REVISION}" && ! "${EXPECTED_REVISION}" =~ ^[0-9a-fA-F]{40}$ ]]; then
        die "--expected-revision must be exactly 40 hexadecimal characters"
    fi
}

validate_checkout_path() {
    case "${CHECKOUT_PATH}" in
        /*) ;;
        *) die "--checkout must be an absolute path" ;;
    esac
    case "${CHECKOUT_PATH}/" in
        *"/../"*|*"/./"*|*"//"*)
            die "--checkout must not contain ., .. or empty path segments"
            ;;
    esac
    case "${CHECKOUT_PATH}" in
        "/"|"${HOME}"|"${HOME}/.local"|"${HOME}/.local/share"|"${HOME}/.local/share/sunofriend")
            die "--checkout is too broad; choose a dedicated child directory"
            ;;
    esac
    if [[ -L "${CHECKOUT_PATH}" ]]; then
        die "--checkout must not be a symbolic link"
    fi
}

require_macos() {
    local system_name
    system_name="$(uname -s)"
    [[ "${system_name}" == "Darwin" ]] || die "this helper supports macOS only (found ${system_name})"
}

find_brew() {
    if command -v brew >/dev/null 2>&1; then
        command -v brew
        return 0
    fi
    if [[ -x /opt/homebrew/bin/brew ]]; then
        printf '%s\n' /opt/homebrew/bin/brew
        return 0
    fi
    if [[ -x /usr/local/bin/brew ]]; then
        printf '%s\n' /usr/local/bin/brew
        return 0
    fi
    return 1
}

find_python311() {
    local brew_path=""
    if command -v python3.11 >/dev/null 2>&1; then
        command -v python3.11
        return 0
    fi
    if brew_path="$(find_brew 2>/dev/null)"; then
        local prefix=""
        if prefix="$("${brew_path}" --prefix python@3.11 2>/dev/null)"; then
            if [[ -x "${prefix}/bin/python3.11" ]]; then
                printf '%s\n' "${prefix}/bin/python3.11"
                return 0
            fi
        fi
    fi
    return 1
}

find_fluidsynth() {
    if command -v fluidsynth >/dev/null 2>&1; then
        command -v fluidsynth
        return 0
    fi
    return 1
}

hash_file() {
    local path="$1"
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "${path}" | awk '{print $1}'
        return 0
    fi
    if command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 "${path}" | awk '{print $NF}'
        return 0
    fi
    die "neither shasum nor openssl is available to verify downloads"
}

soundfont_path() {
    printf '%s\n' "${HOME}/${SOUNDFONT_RELATIVE_PATH}"
}

checkout_origin() {
    git -C "${CHECKOUT_PATH}" remote get-url origin 2>/dev/null
}

validate_existing_checkout() {
    if [[ ! -e "${CHECKOUT_PATH}" ]]; then
        return 0
    fi
    [[ -d "${CHECKOUT_PATH}" ]] || die "checkout path exists and is not a directory: ${CHECKOUT_PATH}"
    [[ -d "${CHECKOUT_PATH}/.git" ]] || die "checkout path exists but is not a Git checkout: ${CHECKOUT_PATH}"
    local origin=""
    origin="$(checkout_origin || true)"
    case "${origin}" in
        "${REPOSITORY_URL}"|"${REPOSITORY_URL_NO_SUFFIX}") ;;
        *)
            die "existing checkout has an unexpected origin (${origin:-none}); it will not be changed"
            ;;
    esac
}

assert_approved_checkout() {
    [[ -d "${CHECKOUT_PATH}/.git" ]] \
        || die "source is not prepared; run --prepare, then review the exact commit before --apply"

    local actual_revision=""
    actual_revision="$(git -C "${CHECKOUT_PATH}" rev-parse HEAD 2>/dev/null || true)"
    [[ "${actual_revision}" == "${EXPECTED_REVISION}" ]] \
        || die "prepared checkout is at ${actual_revision:-no commit}, not approved commit ${EXPECTED_REVISION}; nothing was installed"
    [[ -z "$(git -C "${CHECKOUT_PATH}" status --porcelain)" ]] \
        || die "existing checkout has local changes; commit or move them, or choose a separate checkout path"
    git -C "${CHECKOUT_PATH}" cat-file -e "${EXPECTED_REVISION}^{commit}" 2>/dev/null \
        || die "approved commit is not available in the prepared checkout"
}

print_plan() {
    local brew_path=""
    local python_path=""
    local fluidsynth_path=""
    local sf2=""
    local sf2_hash=""
    local checkout_revision=""

    sf2="$(soundfont_path)"

    say "Sunofriend newcomer setup — inspection only"
    say "No files, packages, repositories or settings are being changed."
    say
    say "Machine"
    say "  macOS:       $(sw_vers -productVersion 2>/dev/null || say unknown)"
    say "  architecture: $(uname -m)"

    say
    say "Checkout"
    say "  target: ${CHECKOUT_PATH}"
    if [[ -d "${CHECKOUT_PATH}/.git" ]]; then
        checkout_revision="$(git -C "${CHECKOUT_PATH}" rev-parse HEAD 2>/dev/null || true)"
        say "  status: expected repository already exists${checkout_revision:+ at ${checkout_revision}}"
        say "  action: preserve it exactly; do not fetch, pull, reset or switch branches"
        if [[ -n "$(git -C "${CHECKOUT_PATH}" status --porcelain 2>/dev/null || true)" ]]; then
            say "  blocker: local checkout changes are present; apply will stop rather than install from an ambiguous source tree"
        fi
    else
        say "  status: not installed"
        say "  next action: prepare may clone the current public ${REPOSITORY_BRANCH} once, validate its origin, then stop"
        say "  note: no dependencies or audio assets are installed until that exact local commit is reviewed and separately approved"
    fi

    say
    say "System tools"
    if brew_path="$(find_brew 2>/dev/null)"; then
        say "  Homebrew: ${brew_path}"
    else
        say "  Homebrew: not found"
        say "  blocker: install Homebrew yourself from https://brew.sh if Python or FluidSynth is missing"
    fi
    if python_path="$(find_python311 2>/dev/null)"; then
        say "  Python 3.11: ${python_path}"
    else
        say "  Python 3.11: missing; apply would run: brew install python@3.11"
    fi
    if fluidsynth_path="$(find_fluidsynth 2>/dev/null)"; then
        say "  FluidSynth: ${fluidsynth_path}"
    else
        say "  FluidSynth: missing; apply would run: brew install fluid-synth"
    fi

    say
    say "Private Python environment"
    if [[ -x "${CHECKOUT_PATH}/.venv/bin/python" ]]; then
        say "  status: existing checkout-local .venv found; apply will verify Python 3.11 before reusing it"
    else
        say "  action: create ${CHECKOUT_PATH}/.venv with Python 3.11"
    fi
    say "  action: build Sunofriend from an immutable Git archive of the approved commit and install its constrained .[all] dependencies from PyPI"
    say "  source safety: installation is non-editable, so later checkout changes cannot alter the installed command"
    say "  meaning: this is the full local feature set, not an optional AI checkpoint"
    say "  observed scale: allow at least 1 GB free for the checkout, environment, tools and temporary download caches"
    say "  time/download: varies with existing tools, network and Mac; the exact total is not knowable before package resolution"

    say
    say "Verified preview instrument"
    say "  target: ${sf2}"
    say "  purpose: approximately 31 MB of neutral instrument sounds so FluidSynth can turn MIDI into a local WAV"
    say "  licence: GeneralUser GS License v2.0 (${SOUNDFONT_LICENSE_URL})"
    say "  notice: the licence permits music creation and documents a sample-origin caveat for commercial software distributors"
    if [[ -f "${sf2}" ]]; then
        sf2_hash="$(hash_file "${sf2}")"
        if [[ "${sf2_hash}" == "${SOUNDFONT_SHA256}" ]]; then
            say "  status: installed and SHA-256 verified"
        else
            say "  status: HASH MISMATCH (${sf2_hash})"
            say "  blocker: apply will stop and will not replace this file"
        fi
    else
        say "  action: download pinned GeneralUser GS and verify SHA-256 before installing"
    fi

    say
    say "Final checks"
    say "  ${CHECKOUT_PATH}/.venv/bin/sunofriend doctor --require convert"
    say "  ${CHECKOUT_PATH}/.venv/bin/sunofriend doctor --require preview"

    say
    say "Network destinations used only after a separately confirmed action"
    say "  github.com                    public Sunofriend source during --prepare"
    say "  raw.githubusercontent.com     pinned GeneralUser GS file during --apply"
    say "  pypi.org / files.pythonhosted.org  constrained Python packages during --apply"
    say "  formulae.brew.sh / ghcr.io or configured Homebrew mirrors  during --apply, only for missing Python 3.11 or FluidSynth"
    say "  note: package services may select CDN or mirror hosts that cannot be enumerated before resolution"

    say
    say "Permissions, interruption and cleanup"
    say "  this helper never invokes sudo"
    say "  an interrupted install leaves inspectable local files and can be resumed; it is not silently rolled back"
    say "  application cleanup: remove ${CHECKOUT_PATH} only after preserving wanted outputs"
    say "  preview-sound cleanup: remove ${sf2}; never remove shared Homebrew packages automatically"

    say
    if [[ "${PREPARE}" -eq 1 ]]; then
        say "Prepare mode requested. The confirmation below allows only the source clone."
    elif [[ "${APPLY}" -eq 1 ]]; then
        say "Apply mode requested for reviewed commit ${EXPECTED_REVISION}."
        say "The confirmation below is the dependency and audio-asset change boundary."
    elif [[ -n "${checkout_revision}" ]]; then
        say "Review this exact local commit. To install it interactively:"
        say "  $(printf '%q' "$0") --apply --expected-revision $(printf '%q' "${checkout_revision}") --checkout $(printf '%q' "${CHECKOUT_PATH}")"
        say "An AI agent may add --yes only after you explicitly approve this exact commit and plan."
    else
        say "Review this source-preparation plan. To clone only the source interactively:"
        say "  $(printf '%q' "$0") --prepare --checkout $(printf '%q' "${CHECKOUT_PATH}")"
        say "Afterwards rerun --plan, review the exact commit, then approve --apply separately."
        say "An AI agent may add --yes only after you explicitly approve the preparation."
    fi
}

confirm_prepare() {
    if [[ "${ASSUME_YES}" -eq 1 ]]; then
        return 0
    fi
    [[ -t 0 ]] || die "--prepare needs an interactive confirmation or --yes after explicit user approval"
    say
    say "This will use the network only to clone the public Sunofriend source."
    say "It will not install packages or audio assets."
    printf 'Type PREPARE to continue: '
    local answer=""
    IFS= read -r answer
    [[ "${answer}" == "PREPARE" ]] || die "confirmation not received; nothing was changed"
}

confirm_apply() {
    if [[ "${ASSUME_YES}" -eq 1 ]]; then
        return 0
    fi
    [[ -t 0 ]] || die "--apply needs an interactive confirmation or --yes after explicit user approval"
    say
    say "This will install from reviewed commit ${EXPECTED_REVISION}, use the network, and may install Homebrew packages."
    printf 'Type INSTALL to continue: '
    local answer=""
    IFS= read -r answer
    [[ "${answer}" == "INSTALL" ]] || die "confirmation not received; nothing was changed"
}

preflight_prepare() {
    command -v git >/dev/null 2>&1 || die "git is required but was not found"
    [[ ! -e "${CHECKOUT_PATH}" ]] \
        || die "checkout already exists; rerun --plan and approve that exact commit instead of preparing again"
}

preflight_apply() {
    local sf2=""
    local actual_hash=""
    local venv_python="${CHECKOUT_PATH}/.venv/bin/python"

    command -v git >/dev/null 2>&1 || die "git is required but was not found"
    command -v curl >/dev/null 2>&1 || die "curl is required but was not found"
    command -v tar >/dev/null 2>&1 || die "tar is required but was not found"
    assert_approved_checkout

    if ! find_python311 >/dev/null 2>&1 || ! find_fluidsynth >/dev/null 2>&1; then
        find_brew >/dev/null 2>&1 \
            || die "Homebrew is required for missing tools. Install it from https://brew.sh, rerun --plan, and approve again."
    fi

    sf2="$(soundfont_path)"
    if [[ -L "${sf2}" ]]; then
        die "SoundFont target is a symbolic link; it will not be changed: ${sf2}"
    fi
    if [[ -f "${sf2}" ]]; then
        actual_hash="$(hash_file "${sf2}")"
        [[ "${actual_hash}" == "${SOUNDFONT_SHA256}" ]] \
            || die "existing SoundFont has the wrong hash and will not be replaced: ${sf2}"
    elif [[ -e "${sf2}" ]]; then
        die "SoundFont target exists but is not a regular file: ${sf2}"
    fi

    if [[ -e "${CHECKOUT_PATH}/.venv" && ! -x "${venv_python}" ]]; then
        die "existing ${CHECKOUT_PATH}/.venv is not a usable virtual environment; it will not be replaced"
    fi
    if [[ -x "${venv_python}" ]]; then
        "${venv_python}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)' \
            || die "existing virtual environment is not Python 3.11; it will not be replaced"
    fi

    if [[ -d "${CHECKOUT_PATH}/.git" ]]; then
        git -C "${CHECKOUT_PATH}" rev-parse --verify HEAD >/dev/null 2>&1 \
            || die "existing checkout has no committed revision; it will not be used"
        [[ -f "${CHECKOUT_PATH}/constraints-audio-macos.txt" ]] \
            || die "existing checkout is missing constraints-audio-macos.txt"
        [[ -f "${CHECKOUT_PATH}/pyproject.toml" ]] \
            || die "existing checkout is missing pyproject.toml"
    fi
}

ensure_system_dependencies() {
    local brew_path=""
    local packages=()

    if ! find_python311 >/dev/null 2>&1; then
        packages+=("python@3.11")
    fi
    if ! find_fluidsynth >/dev/null 2>&1; then
        packages+=("fluid-synth")
    fi
    if [[ "${#packages[@]}" -eq 0 ]]; then
        say "System tools already present; Homebrew install skipped."
        return 0
    fi
    brew_path="$(find_brew 2>/dev/null || true)"
    [[ -n "${brew_path}" ]] || die "Homebrew is required for missing tools. Install it from https://brew.sh, rerun --plan, and approve again."
    say "Installing missing Homebrew package(s): ${packages[*]}"
    "${brew_path}" install "${packages[@]}"
    find_python311 >/dev/null 2>&1 || die "Python 3.11 is still unavailable after Homebrew completed"
    find_fluidsynth >/dev/null 2>&1 || die "FluidSynth is still unavailable after Homebrew completed"
}

ensure_checkout() {
    if [[ -d "${CHECKOUT_PATH}/.git" ]]; then
        say "Existing Sunofriend checkout preserved; no network update performed."
        return 0
    fi

    local parent=""
    parent="$(dirname "${CHECKOUT_PATH}")"
    mkdir -p -- "${parent}"
    TEMP_CLONE="${CHECKOUT_PATH}.bootstrap.$$"
    [[ ! -e "${TEMP_CLONE}" ]] || die "temporary clone path already exists: ${TEMP_CLONE}"

    say "Cloning the public Sunofriend repository into a temporary directory."
    git clone \
        --origin origin \
        --branch "${REPOSITORY_BRANCH}" \
        --single-branch \
        -- "${REPOSITORY_URL}" "${TEMP_CLONE}"

    local cloned_origin=""
    cloned_origin="$(git -C "${TEMP_CLONE}" remote get-url origin 2>/dev/null || true)"
    [[ "${cloned_origin}" == "${REPOSITORY_URL}" ]] || die "cloned repository origin did not match the pinned public URL"
    [[ ! -e "${CHECKOUT_PATH}" ]] || die "checkout target appeared during clone; refusing to replace it"
    mv -- "${TEMP_CLONE}" "${CHECKOUT_PATH}"
    TEMP_CLONE=""
}

ensure_venv_and_python_packages() {
    local python311=""
    local venv="${CHECKOUT_PATH}/.venv"
    local venv_python="${venv}/bin/python"
    python311="$(find_python311 2>/dev/null || true)"
    [[ -n "${python311}" ]] || die "Python 3.11 is not available"
    assert_approved_checkout

    TEMP_APPROVED_SOURCE="$(mktemp -d "${TMPDIR:-/tmp}/sunofriend-approved-source.XXXXXX")"
    git -C "${CHECKOUT_PATH}" archive "${EXPECTED_REVISION}" \
        | tar -xf - -C "${TEMP_APPROVED_SOURCE}"
    [[ -f "${TEMP_APPROVED_SOURCE}/constraints-audio-macos.txt" ]] \
        || die "approved source archive is missing constraints-audio-macos.txt"
    [[ -f "${TEMP_APPROVED_SOURCE}/pyproject.toml" ]] \
        || die "approved source archive is missing pyproject.toml"

    if [[ -e "${venv}" && ! -x "${venv_python}" ]]; then
        die "existing ${venv} is not a usable virtual environment; move it aside manually and rerun"
    fi
    if [[ ! -e "${venv}" ]]; then
        say "Creating the private Python 3.11 environment."
        "${python311}" -m venv "${venv}"
    fi
    "${venv_python}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)' \
        || die "existing virtual environment is not Python 3.11; it was not replaced"

    say "Installing approved Sunofriend source and its constrained audio dependencies."
    (
        cd "${TEMP_APPROVED_SOURCE}"
        PIP_DISABLE_PIP_VERSION_CHECK=1 "${venv_python}" -m ensurepip --upgrade
        PIP_DISABLE_PIP_VERSION_CHECK=1 "${venv_python}" -m pip install \
            -c constraints-audio-macos.txt \
            '.[all]'
    )
    rm -rf -- "${TEMP_APPROVED_SOURCE}"
    TEMP_APPROVED_SOURCE=""
}

ensure_soundfont() {
    local target=""
    local parent=""
    local partial=""
    local actual_hash=""
    target="$(soundfont_path)"
    parent="$(dirname "${target}")"

    if [[ -L "${target}" ]]; then
        die "SoundFont target is a symbolic link; it will not be changed: ${target}"
    fi
    if [[ -f "${target}" ]]; then
        actual_hash="$(hash_file "${target}")"
        [[ "${actual_hash}" == "${SOUNDFONT_SHA256}" ]] \
            || die "existing SoundFont has the wrong hash and will not be replaced: ${target}"
        say "GeneralUser GS already installed and verified."
        return 0
    fi
    [[ ! -e "${target}" ]] || die "SoundFont target exists but is not a regular file: ${target}"

    mkdir -p -- "${parent}"
    partial="${target}.partial.$$"
    [[ ! -e "${partial}" ]] || die "temporary SoundFont path already exists: ${partial}"
    TEMP_SOUNDFONT="${partial}"
    say "Downloading the pinned GeneralUser GS SoundFont."
    curl \
        --proto '=https' \
        --tlsv1.2 \
        --fail \
        --location \
        --silent \
        --show-error \
        "${SOUNDFONT_URL}" \
        --output "${partial}"
    actual_hash="$(hash_file "${partial}")"
    if [[ "${actual_hash}" != "${SOUNDFONT_SHA256}" ]]; then
        rm -f -- "${partial}"
        die "downloaded SoundFont failed SHA-256 verification"
    fi
    chmod 0644 "${partial}"
    [[ ! -e "${target}" ]] || die "SoundFont target appeared during download; refusing to replace it"
    mv -- "${partial}" "${target}"
    TEMP_SOUNDFONT=""
}

run_doctors() {
    local executable="${CHECKOUT_PATH}/.venv/bin/sunofriend"
    [[ -x "${executable}" ]] || die "Sunofriend command was not installed in the private environment"
    say "Checking stem conversion support."
    "${executable}" doctor --require convert
    say "Checking offline MIDI preview support."
    "${executable}" doctor --require preview
}

print_next_steps() {
    cat <<EOF

Sunofriend is ready.

Nothing was uploaded, no existing checkout was updated, and no live MIDI
device was required. The installed source revision is:
  ${EXPECTED_REVISION}

No stems yet? Ask the Sunofriend skill to choose a fresh location and run:
  "${CHECKOUT_PATH}/.venv/bin/sunofriend" demo --out-dir "/absolute/fresh/demo-output"

Already have authorised top-level WAV stems? Ask the skill to run:
  "${CHECKOUT_PATH}/.venv/bin/sunofriend" create "/absolute/path/to/My Song-B minor-113bpm-440hz" --out-dir "/absolute/fresh/song-output"

Both commands create an automatic, explicitly unreviewed first pass with
editable MIDI, a balanced MIDI-derived interpretation WAV and a starter ZIP.
Use the TUI's Studio mode later when you want to compare methods and make your
own choices.

Installed checkout:
  ${CHECKOUT_PATH}
EOF
}

print_prepared_next_steps() {
    local prepared_revision=""
    prepared_revision="$(git -C "${CHECKOUT_PATH}" rev-parse HEAD)"
    cat <<EOF

Sunofriend source is prepared, but nothing has been installed.

Prepared checkout:
  ${CHECKOUT_PATH}
Exact source commit:
  ${prepared_revision}

Rerun the helper with --plan. Review the exact commit and remaining package,
download and machine changes. Only then approve --apply with:
  $(printf '%q' "$0") --apply --expected-revision ${prepared_revision} --checkout $(printf '%q' "${CHECKOUT_PATH}")
EOF
}

main() {
    parse_args "$@"
    validate_checkout_path
    require_macos
    validate_existing_checkout
    print_plan
    if [[ "${PREPARE}" -eq 1 ]]; then
        preflight_prepare
        confirm_prepare
        ensure_checkout
        print_prepared_next_steps
        exit 0
    fi
    if [[ "${APPLY}" -ne 1 ]]; then
        exit 0
    fi
    preflight_apply
    confirm_apply
    assert_approved_checkout
    ensure_system_dependencies
    assert_approved_checkout
    ensure_venv_and_python_packages
    ensure_soundfont
    run_doctors
    print_next_steps
}

main "$@"
