import type { Metadata } from "next";
import Link from "next/link";
import { links } from "../content";

export const metadata: Metadata = {
  title: "Windows setup notes",
  description:
    "Reproducible Sunofriend setup findings from a native Windows 11 x64 trial, including the working diagnostics and the current fcntl blocker.",
  alternates: {
    canonical: "/windows/",
  },
};

const installCommands = `git clone https://github.com/N9-Developer-Empowerment/sunofriend.git
Set-Location sunofriend
uv python install 3.11
uv venv --python 3.11 .venv-windows
uv pip install --python .venv-windows\\Scripts\\python.exe ".[all]"`;

const toolCommands = `$env:SUNOFRIEND_FLUIDSYNTH = "C:\\Tools\\fluidsynth\\bin\\fluidsynth.exe"
$env:SUNOFRIEND_SF2 = "C:\\Tools\\soundfonts\\GeneralUser-GS.sf2"
$env:SUNOFRIEND_FFMPEG = "C:\\Tools\\ffmpeg\\bin\\ffmpeg.exe"
$env:SUNOFRIEND_FFPROBE = "C:\\Tools\\ffmpeg\\bin\\ffprobe.exe"
(Get-FileHash $env:SUNOFRIEND_SF2 -Algorithm SHA256).Hash`;

const checkCommands = `.\\.venv-windows\\Scripts\\sunofriend.exe --version
.\\.venv-windows\\Scripts\\sunofriend.exe doctor --require convert
.\\.venv-windows\\Scripts\\sunofriend.exe doctor --require preview
.\\.venv-windows\\Scripts\\sunofriend.exe source-doctor`;

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
          <span className="card-number">PARTIALLY VERIFIED · 16 AUGUST 2026</span>
          <h2 id="status-title">Diagnostics pass; demo and create do not.</h2>
          <p>
            On Windows 11 x64, Sunofriend 0.4.0 source at commit
            <code> 95ca8cf</code> installed in an isolated Python 3.11
            environment. Conversion, preview rendering and source-import
            diagnostics passed with local audio tools.
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
            </article>
          </div>
          <div className="prompt-stack">
            <CommandBox label="POWERSHELL · FROM YOUR WORK FOLDER" value={installCommands} rows={7} />
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
            <CommandBox label="POWERSHELL · READ-ONLY CHECKS" value={checkCommands} rows={6} />
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
                FFprobe without network access.
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

        <section id="blocker">
          <h2>4. Stop at the current native-Windows blocker</h2>
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
