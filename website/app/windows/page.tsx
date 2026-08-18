import type { Metadata } from "next";
import Link from "next/link";
import { links } from "../content";

export const metadata: Metadata = {
  title: "Windows setup notes",
  description:
    "Reproducible native Windows 11 setup findings for Sunofriend and local ACE-Step song generation, including current limits.",
  alternates: {
    canonical: "/windows/",
  },
};

const installCommands = `git clone https://github.com/N9-Developer-Empowerment/sunofriend.git
Set-Location sunofriend
uv python install 3.11
uv venv --python 3.11 .venv-windows
uv pip install --python .venv-windows\\Scripts\\python.exe ".[all]"
uv pip uninstall --python .venv-windows\\Scripts\\python.exe tensorflow tensorflow-intel tensorflow-estimator tensorflow-io-gcs-filesystem`;

const toolCommands = `$env:SUNOFRIEND_FLUIDSYNTH = "C:\\Tools\\fluidsynth\\bin\\fluidsynth.exe"
$env:SUNOFRIEND_SF2 = "C:\\Tools\\soundfonts\\GeneralUser-GS.sf2"
$env:SUNOFRIEND_FFMPEG = "C:\\Tools\\ffmpeg\\bin\\ffmpeg.exe"
$env:SUNOFRIEND_FFPROBE = "C:\\Tools\\ffmpeg\\bin\\ffprobe.exe"
(Get-FileHash $env:SUNOFRIEND_SF2 -Algorithm SHA256).Hash`;

const checkCommands = `.\\.venv-windows\\Scripts\\sunofriend.exe --version
.\\.venv-windows\\Scripts\\sunofriend.exe doctor --require convert
.\\.venv-windows\\Scripts\\sunofriend.exe doctor --require preview
.\\.venv-windows\\Scripts\\sunofriend.exe source-doctor
.\\.venv-windows\\Scripts\\sunofriend-separate.exe profiles
.\\.venv-windows\\Scripts\\sunofriend-separate.exe doctor`;

const aceStepCommands = `git clone https://github.com/ACE-Step/ACE-Step-1.5.git
Set-Location ACE-Step-1.5
uv sync
$env:PYTHONUTF8 = "1"
$env:ACESTEP_CONFIG_PATH = "acestep-v15-base"
$env:ACESTEP_OFFLOAD_TO_CPU = "true"
.\\.venv\\Scripts\\acestep-api.exe --host 127.0.0.1 --port 8001 --init-llm --lm-model-path acestep-5Hz-lm-0.6B`;

const generationCommands = `$style = Get-Content -LiteralPath "C:\\Music\\style.txt" -Raw
$generationArgs = @(
  "song-generate", "C:\\Music\\reference.wav",
  "--lyrics", "C:\\Music\\lyrics.txt", "--style", $style,
  "--reference-strength", "0.35", "--style-strength", "0.75",
  "--bpm", "120", "--key", "A Major", "--time-signature", "4/4",
  "--out-dir", "C:\\Music\\generation-01", "--execute", "--confirm-rights"
)
& .\\.venv-windows\\Scripts\\sunofriend.exe @generationArgs`;

const remixCommands = `$style = Get-Content -LiteralPath "C:\\Music\\style.txt" -Raw
$remixArgs = @(
  "song-generate", "C:\\Music\\reference.wav",
  "--lyrics", "C:\\Music\\lyrics-clean.txt", "--style", $style,
  "--reference-strength", "0.2", "--style-strength", "0.8",
  "--generation-mode", "remix",
  "--out-dir", "C:\\Music\\native-remix-01", "--execute", "--confirm-rights"
)
& .\\.venv-windows\\Scripts\\sunofriend.exe @remixArgs`;

const demucsCommands = `uv venv --python 3.11 .venv-demucs-windows
uv pip install --link-mode copy --python .venv-demucs-windows\\Scripts\\python.exe torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
uv pip install --link-mode copy --python .venv-demucs-windows\\Scripts\\python.exe demucs==4.0.1 SoundFile==0.13.1
$env:TORCH_HOME = "C:\\Tools\\models\\demucs"
$env:PYTORCH_NO_CUDA_MEMORY_CACHING = "1"
& .\\.venv-demucs-windows\\Scripts\\python.exe -m demucs.separate -n htdemucs_ft --two-stems vocals --float32 -d cuda --shifts 1 --overlap 0.25 --segment 7 -o "C:\\Music\\demucs-review" "C:\\Music\\reference.wav"`;

function CommandBox({ label, value, rows }: { label: string; value: string; rows: number }) {
  return (
    <div className="prompt-box">
      <div className="prompt-top">
        <span>{label}</span>
      </div>
      <textarea aria-label={label} readOnly value={value} rows={rows} />
    </div>
  );
}

export default function WindowsSetup() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Windows guide navigation">
          <a href="#status">Status</a>
          <a href="#install">Install</a>
          <a href="#tools">Audio tools</a>
          <a href="#check">Check</a>
          <a href="#local-ai">Local AI</a>
          <a href="#blocker">Blocker</a>
        </nav>
        <a className="header-cta" href={links.compatibility}>
          Report a result
        </a>
      </header>

      <article className="agent-page guide-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            NATIVE WINDOWS TRIAL NOTES
          </div>
          <h1>Windows setup: what worked, and what stops next.</h1>
          <p className="lede">
            These notes record a real native Windows 11 x64 setup trial. They
            make dependency installation reproducible without claiming that
            the complete Sunofriend workflow is supported on Windows yet.
          </p>
          <div className="hero-actions">
            <a className="button button-hot" href="#install">
              Read the setup notes
            </a>
            <a className="button button-ghost" href={links.compatibility}>
              Send compatibility feedback ↗
            </a>
          </div>
        </header>

        <section id="status" className="status-panel" aria-labelledby="status-title">
          <span className="card-number">PARTIALLY VERIFIED · 18 AUGUST 2026</span>
          <h2 id="status-title">Diagnostics pass; demo and create do not.</h2>
          <p>
            The initial Windows 11 x64 trial installed Sunofriend 0.4.0 source
            at commit <code>95ca8cf</code> in an isolated Python 3.11
            environment. Conversion, preview rendering and source-import
            diagnostics passed with local audio tools. A follow-up on the
            current Windows feature branch made the public separation profile
            and doctor commands load instead of crashing at their former
            top-level <code>fcntl</code> import.
          </p>
          <p>
            The normal demo then stopped before conversion with
            <code> No module named &apos;fcntl&apos;</code>. The source-graph locking
            code currently imports the POSIX-only <code>fcntl</code> module.
            Native Windows should therefore be treated as a partially verified
            development path, not a working release route.
          </p>
          <p className="guide-note">
            The experimental two-stem and core-four separators remain supported
            only on the documented Apple-silicon macOS route. Windows Subsystem
            for Linux has not been tested in this trial.
          </p>
        </section>

        <section id="install">
          <h2>1. Create an isolated Python 3.11 environment</h2>
          <div className="agent-grid">
            <article className="agent-card">
              <span className="card-number">WHY UV</span>
              <h3>Avoid depending on system Python</h3>
              <p>
                The successful trial used a uv-managed CPython 3.11 and a
                repository-local <code>.venv-windows</code>. Install uv from
                its official instructions, then run the commands alongside.
              </p>
              <div className="journey-links">
                <a className="text-link" href={links.uvInstall}>
                  Official uv installation guide ↗
                </a>
              </div>
            </article>
            <article className="agent-card">
              <span className="card-number">CURRENT LIMIT</span>
              <h3>This installs dependencies, not Windows support</h3>
              <p>
                Package installation completed successfully in the trial. Do
                not interpret that as proof that demo, create, Studio or the
                terminal UI can complete on native Windows.
              </p>
              <p>
                Basic Pitch 0.4 otherwise installs TensorFlow 2.14 on Python
                3.11 Windows, which is incompatible with this project&apos;s NumPy
                2 runtime. The final uninstall line keeps the installed ONNX
                Runtime path and removes only those incompatible TensorFlow
                extras.
              </p>
            </article>
          </div>
          <div className="prompt-stack">
            <CommandBox label="POWERSHELL · FROM YOUR WORK FOLDER" value={installCommands} rows={8} />
          </div>
        </section>

        <section id="tools">
          <h2>2. Point Sunofriend at the local audio tools</h2>
          <p className="lede">
            Install trusted Windows builds of FFmpeg/FFprobe and FluidSynth,
            then download the exact GeneralUser GS SoundFont used by the
            project. Review each provider&apos;s licence before redistribution.
          </p>
          <div className="agent-grid">
            <article className="agent-card">
              <span className="card-number">AUDIO BINARIES</span>
              <h3>Use official project starting points</h3>
              <ul>
                <li><a href={links.ffmpegDownload}>FFmpeg download guidance ↗</a></li>
                <li><a href={links.fluidSynthReleases}>FluidSynth releases ↗</a></li>
                <li><a href={links.soundFont}>Pinned GeneralUser GS file ↗</a></li>
                <li><a href={links.soundFontLicense}>GeneralUser GS licence ↗</a></li>
              </ul>
            </article>
            <article className="agent-card">
              <span className="card-number">PINNED SOUND</span>
              <h3>Verify the SoundFont</h3>
              <p>
                The expected SHA-256 is
                <code> 9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe</code>.
                Check the downloaded file before using it.
              </p>
            </article>
          </div>
          <p className="guide-note">
            In the tested coding-agent environment, changing only
            <code> PATH</code> was not reliably inherited by child Python
            processes. The four exact, per-PowerShell-session variables below
            were reliable. Replace the example paths with your own files.
          </p>
          <div className="prompt-stack">
            <CommandBox label="POWERSHELL · EXACT LOCAL TOOL PATHS" value={toolCommands} rows={7} />
          </div>
        </section>

        <section id="check">
          <h2>3. Check only the capabilities you need</h2>
          <div className="prompt-stack">
            <CommandBox label="POWERSHELL · READ-ONLY CHECKS" value={checkCommands} rows={8} />
          </div>
          <div className="agent-grid">
            <article className="agent-card">
              <span className="card-number">OBSERVED PASS</span>
              <h3>Offline conversion and preview were ready</h3>
              <p>
                <code>transcribe_ready</code>, <code>convert_ready</code>,
                <code>preview_ready</code>, <code>render_ready</code> and
                <code>requirement_ready</code> were true. The render smoke test
                produced audio, and <code>source-doctor</code> found FFmpeg and
                FFprobe without network access. With TensorFlow removed, the
                Basic Pitch ONNX tracker also completed a full-song consensus
                pass with pYIN.
              </p>
            </article>
            <article className="agent-card">
              <span className="card-number">EXPECTED FALSE</span>
              <h3>CoreMIDI is not an offline-file requirement</h3>
              <p>
                The overall report can still show <code>ready: false</code> and
                <code>midi_ready: false</code> because Windows has no CoreMIDI
                live-playback destination. For these checks, use
                <code> requirement_ready</code> to judge the requested offline
                capability. This does not clear the separate <code>fcntl</code>
                blocker.
              </p>
            </article>
          </div>
        </section>

        <section id="local-ai">
          <h2>4. Run local ACE-Step song generation</h2>
          <p className="lede">
            The separate <code>song-generate</code> path completed a native
            Windows test on an RTX 4080 Laptop GPU with 12 GB VRAM. ACE-Step
            Base plus the 0.6B language model produced two 232-second
            creative-reference songs in one request and two 237.56-second
            native cover/remix candidates in another. The remix request took
            about 112 seconds wall time. These are one machine&apos;s execution
            results, not performance or musical-quality guarantees.
          </p>
          <div className="prompt-stack">
            <CommandBox label="POWERSHELL · INSTALL AND START ACE-STEP API" value={aceStepCommands} rows={9} />
            <CommandBox label="POWERSHELL · CREATIVE-REFERENCE MODE" value={generationCommands} rows={11} />
            <CommandBox label="POWERSHELL · NATIVE COVER/REMIX MODE" value={remixCommands} rows={11} />
            <CommandBox label="POWERSHELL · OPTIONAL ISOLATED DEMUCS RESEARCH" value={demucsCommands} rows={10} />
          </div>
          <div className="agent-grid">
            <article className="agent-card">
              <span className="card-number">WINDOWS CONSOLE</span>
              <h3>Keep UTF-8 mode enabled</h3>
              <p>
                Without <code>PYTHONUTF8=1</code>, ACE-Step successfully wrote
                a smoke-test WAV and then the Windows CP1252 console failed
                while printing a Unicode status symbol. UTF-8 mode made the
                same command exit cleanly.
              </p>
            </article>
            <article className="agent-card">
              <span className="card-number">12 GB VRAM</span>
              <h3>Start with Base and the 0.6B LM</h3>
              <p>
                CPU offload left enough headroom for two long candidates. This
                is the first verified configuration; larger XL or language
                models need a separate memory and quality comparison.
              </p>
            </article>
          </div>
          <p className="guide-note">
            In the OneDrive-based trial, the vLLM/Triton cache failed while
            creating a temporary compiler file. ACE-Step automatically fell
            back to its PyTorch language-model backend and completed the songs.
            Prefer a short, non-synchronised checkout/cache path for future
            trials. Sunofriend now streams reference audio as a multipart file;
            current ACE-Step rejects client-supplied absolute audio paths.
          </p>
          <p className="guide-note">
            Planning is read-only. <code>--execute --confirm-rights</code> is
            required before the local API receives audio. Default reference
            mode uses ACE-Step <code>text2music</code>. In that mode, omit BPM,
            key, time signature or duration to let ACE-Step infer the value;
            supplied values are sent as explicit metadata. Native remix mode
            uses ACE-Step <code>cover</code>, uploads the source as
            <code> src_audio</code>, accepts replacement lyrics and locks the
            result to the source duration. Sunofriend rejects BPM, key, meter
            or duration locks in remix mode rather than claiming unsupported
            controls. Every run writes two candidates plus hash-bound request
            and receipt files to a fresh output folder.
          </p>
          <p className="guide-note">
            The original track is the primary musical input. Lyrics supply the
            words and style changes production; neither is allowed to erase the
            source identity. At non-zero reference strength, a result with no
            recognisable melodic, rhythmic, harmonic, structural or performance
            connection fails as a remix. Provider qualification also requires a
            matched no-reference comparison to prove the upload changed the music.
          </p>
          <p className="guide-note">
            Keep production prose in the style description and only concise
            section or performance tags in the lyric file. Exact lyric-text
            transport does not prove that every word was sung. The retained
            native-remix pair was subsequently rejected by the musician: its
            vocals were in tune but flat and talk-sung, its accompaniment was
            unmusical, and neither candidate was enjoyable or creative. Do not
            interpret successful execution as a qualified Suno replacement.
          </p>
          <p className="guide-note">
            The bounded track-level experiment also failed. One ACE-Step Base
            completion retained the original out-of-tune vocal; the other was
            an unrelated instrumental with no audible melody or likeness from
            the input. Neither advances to stems or MIDI, and track tasks are
            not exposed as a public Sunofriend command. A final intentional
            Turbo pair improved vocal tuning and backing musicality, but neither
            result retained an audible connection to the original melody or
            rhythm. Turbo also ignores the independent style-strength guidance.
            ACE-Step is therefore executable but rejected as the full-song remix
            provider for this fixture. A later vocal-derived MIDI scaffold was
            also rejected: the rough singing did not carry the intended melody,
            so literal F0 became fragmented random notes and detected accents did
            not form a musical beat. Do not use that scaffold for generation.
            The corrected private route starts from vocal-suppressed accompaniment
            and validates the retained instrumental music before any MIDI step.
          </p>
          <p className="guide-note">
            The optional Demucs commands above reproduce one separate research
            environment; they do not add a supported Windows separator to
            Sunofriend. The tested RTX 4080 run used PyTorch 2.7.1 CUDA 12.8,
            Demucs 4.0.1 and the four-model <code>htdemucs_ft</code> ensemble.
            OneDrive required <code>--link-mode copy</code>, and Demucs required
            the integer <code>--segment 7</code>. Listen to the source,
            <code> vocals.wav</code> and <code> no_vocals.wav</code> before
            analysing motifs, chords, bass, groove or structure.
          </p>
        </section>

        <section id="blocker">
          <h2>5. Stop at the current full-workflow blocker</h2>
          <div className="agent-grid">
            <article className="agent-card">
              <span className="card-number">FIRST REPRODUCIBLE FAILURE</span>
              <h3><code>sunofriend: No module named &apos;fcntl&apos;</code></h3>
              <p>
                The demo creates its synthetic-stem staging folder, then fails
                while importing the source-lineage lock. Treat any partial
                folder from this failure as incomplete output.
              </p>
            </article>
            <article className="agent-card">
              <span className="card-number">DO NOT PAPER OVER IT</span>
              <h3>The fix belongs in Sunofriend</h3>
              <p>
                Do not install an unrelated package merely named
                <code> fcntl</code>. Sunofriend needs a tested cross-platform
                exclusive-lock abstraction and Windows tests. Until that lands,
                use the supported macOS route for complete production work.
              </p>
            </article>
          </div>
          <p className="guide-note">
            If you repeat the trial, report the Sunofriend commit, Windows
            edition, architecture, Python version, exact command and first
            error. Do not attach stems, private music, filenames or metadata.
            The working local song-generation path does not clear the separate
            source-lineage locking blocker used by demo, create and Studio.
            Broader AI-session tests also encounter the POSIX-only
            <code> resource</code> module, so passing <code>song-generate</code>
            must not be generalised into full native-Windows support.
          </p>
        </section>

        <div className="journey-links back-link">
          <Link className="text-link" href="/">
            ← Back to Sunofriend
          </Link>
          <a className="text-link text-link-muted" href={links.compatibility}>
            Send a compatibility report ↗
          </a>
        </div>
      </article>
    </main>
  );
}
