import Link from "next/link";
import Image from "next/image";
import { CopyPrompt } from "./copy-prompt";
import {
  agentSummary,
  links,
  newcomerPrompt,
  skillInstallPrompt,
} from "./content";

const ExternalLink = ({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) => (
  <a href={href} className={className} target="_blank" rel="noreferrer">
    {children}
  </a>
);

const softwareJsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Sunofriend",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "macOS",
  isAccessibleForFree: true,
  description: agentSummary,
  downloadUrl: links.repo,
  installUrl: links.skill,
  license: links.license,
  codeRepository: links.repo,
  creator: {
    "@type": "Organization",
    name: "Unsigned Media Ltd",
  },
  featureList: [
    "Authorised WAV stems to editable MIDI",
    "Balanced MIDI-derived song-interpretation WAV",
    "Starter ZIP for a DAW handoff",
    "Simple automatic mode",
    "Studio multi-method comparison",
    "Local processing on macOS",
  ],
};

export default function Home() {
  return (
    <main id="top">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareJsonLd) }}
      />
      <div className="noise" aria-hidden="true" />

      <header className="site-header">
        <a className="wordmark" href="#top" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#codex">Start</a>
          <a href="#choose">Choose a route</a>
          <a href="#demo">Try the demo</a>
          <Link href="/for-agents">For AI agents</Link>
        </nav>
        <a className="header-cta" href="#codex">
          Use with Codex <span aria-hidden="true">↓</span>
        </a>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            LOCAL MUSIC TOOL FOR MAC
          </div>
          <h1 id="hero-title">
            Hear the song.
            <span>Change the parts.</span>
          </h1>
          <p className="hero-proof">Let Codex guide the setup.</p>
          <p className="hero-lede">
            Sunofriend listens to separate drums, bass, keys, vocals and other
            song parts. It gives you editable MIDI and a clean instrumental
            interpretation you can hear before opening your music software.
          </p>
          <div className="hero-actions">
            <a className="button button-hot" href="#codex">
              Start with the skill <span aria-hidden="true">↓</span>
            </a>
            <ExternalLink className="button button-ghost" href={links.outOfPlace}>
              <span className="play-mark" aria-hidden="true">▶</span>
              Hear an example
            </ExternalLink>
          </div>
          <ul className="signal-list" aria-label="Sunofriend principles">
            <li>AUDIO STAYS ON YOUR MAC</li>
            <li>FIRST RESULT IS AUTOMATIC</li>
            <li>YOU CAN GO DEEPER LATER</li>
          </ul>
        </div>

        <div className="hero-visual">
          <Image
            src="/brand/sunofriend-listener-banner.png"
            alt="A waveform becoming the Sunofriend mark and editable MIDI notes"
            width={1672}
            height={941}
            priority
            unoptimized
          />
          <div className="hero-stamp" aria-hidden="true">
            <span>STEMS</span>
            <b>→</b>
            <span>MIDI + WAV</span>
          </div>
        </div>
      </section>

      <div className="plain-strip">
        <strong>You do not need to understand Python.</strong>
        <span>
          You need a Mac and Codex with local workspace access for the guided
          route. To use your own song, you also need music you are allowed to
          process.
        </span>
      </div>

      <section id="codex" className="codex-start section-shell" aria-labelledby="codex-title">
        <div className="section-index">01 / EASIEST WAY IN</div>
        <div className="section-heading-row">
          <div>
            <p className="kicker">INSTALL THE GUIDE BEFORE THE TOOL.</p>
            <h2 id="codex-title">Give this job to Codex.</h2>
          </div>
          <p>
            The Sunofriend skill tells an AI coding agent what the tool can do,
            what must stay local and which questions to ask before it changes
            anything on your Mac.
          </p>
        </div>
        <div className="codex-grid">
          <div className="prompt-stack">
            <CopyPrompt
              prompt={skillInstallPrompt}
              label="TURN 1 / INSTALL THE SKILL"
            />
            <CopyPrompt
              prompt={newcomerPrompt}
              label="TURN 2 / USE SUNOFRIEND"
            />
            <p className="prompt-help">
              <strong>Do not clone the repository first.</strong> If
              <code>$sunofriend</code> is not recognised after turn 1, restart
              Codex once and send turn 2 again.
            </p>
          </div>
          <aside className="what-happens">
            <span className="card-number">WHAT HAPPENS NEXT</span>
            <ol>
              <li>
                <strong>First turn: install only the skill.</strong>
                <span>
                  Codex confirms the guide is available, then stops before
                  installing the app or audio dependencies.
                </span>
              </li>
              <li>
                <strong>Second turn: use $sunofriend.</strong>
                <span>
                  The installed skill checks your Mac, explains missing
                  software, asks before preparing the source, then asks again
                  before installing the exact reviewed commit.
                </span>
              </li>
              <li>
                <strong>You choose your starting point.</strong>
                <span>Existing stems, help finding stems or the worked demo.</span>
              </li>
              <li>
                <strong>The beginner route makes a first result.</strong>
                <span>
                  Codex can use the focused create or demo command; the TUI
                  offers the same outcome through Simple mode. MIDI, a listening
                  WAV and a ZIP stay automatic and unreviewed.
                </span>
              </li>
            </ol>
            <ExternalLink className="text-link" href={links.skill}>
              See the official skill <span aria-hidden="true">↗</span>
            </ExternalLink>
          </aside>
        </div>
      </section>

      <section id="choose" className="journeys section-shell" aria-labelledby="choose-title">
        <div className="section-index">02 / WHERE ARE YOU STARTING?</div>
        <div className="section-heading-row">
          <h2 id="choose-title">Pick the sentence that sounds like you.</h2>
          <p>
            After the two prompts above, Codex should offer these same three
            routes one at a time.
          </p>
        </div>
        <div className="journey-grid">
          <article id="have-stems" className="journey-card journey-primary">
            <span className="card-number">A / I HAVE STEMS</span>
            <h3>I already have separate WAV files.</h3>
            <p>
              Give Codex the folder location. It will check that the files sit
              together, confirm or ask you for the song key and BPM, and prepare
              a fresh output folder.
            </p>
            <ul>
              <li>Best when you already export separate parts</li>
              <li>Use music you own or can process</li>
              <li>Codex uses the focused create command</li>
            </ul>
            <a className="text-link" href="#codex">
              Copy the starter prompt ↑
            </a>
          </article>

          <article id="need-stems" className="journey-card">
            <span className="card-number">B / I NEED STEMS</span>
            <h3>I only have a finished song.</h3>
            <p>
              Sunofriend does not separate a mixed song. Codex can explain how
              to export your own DAW parts or use a separate stem service such
              as Moises or Suno, subject to that service&apos;s terms.
            </p>
            <div className="journey-links">
              <ExternalLink className="text-link" href={links.moisesExportHelp}>
                Moises export help ↗
              </ExternalLink>
              <ExternalLink className="text-link text-link-muted" href={links.sunoStemHelp}>
                Suno stem help ↗
              </ExternalLink>
            </div>
            <small>
              Never upload or process music unless you have the necessary rights.
            </small>
          </article>

          <article id="want-demo" className="journey-card">
            <span className="card-number">C / I WANT THE DEMO</span>
            <h3>I want to try it without personal music or paid stems.</h3>
            <p>
              Let Codex run a copyright-safe synthetic stem project through the
              real automatic pipeline. Then hear the result and explore the
              included worked MIDI pack.
            </p>
            <div className="journey-links">
              <Link className="text-link" href="/demo">
                Get the guided demo instructions →
              </Link>
              <ExternalLink className="text-link text-link-muted" href={links.outOfPlace}>
                Hear Out of Place ↗
              </ExternalLink>
            </div>
            <small>
              The built-in demo writes only to a fresh folder you approve.
            </small>
          </article>
        </div>
      </section>

      <section className="results section-shell" aria-labelledby="results-title">
        <div className="section-index">03 / WHAT YOU GET</div>
        <div className="section-heading-row">
          <h2 id="results-title">A song you can hear and parts you can change.</h2>
          <p>
            The first result is deliberately useful before you learn the deeper
            Studio workflow.
          </p>
        </div>
        <div className="result-grid">
          <article>
            <span className="result-mark">♪</span>
            <h3>Editable MIDI</h3>
            <p>
              Separate note files for the parts Sunofriend could interpret.
              Change notes, timing and instruments in GarageBand or another DAW.
            </p>
          </article>
          <article>
            <span className="result-mark">▶</span>
            <h3>Listening WAV</h3>
            <p>
              A balanced MIDI-derived interpretation for hearing the whole idea.
              The source stems are level references, not audio in this mix.
            </p>
          </article>
          <article>
            <span className="result-mark">↓</span>
            <h3>Starter ZIP</h3>
            <p>
              The individual MIDI, combined MIDI, WAV, receipt and short start
              guide in one clearly labelled automatic, unreviewed bundle.
            </p>
          </article>
        </div>
      </section>

      <section id="demo" className="demo section-shell" aria-labelledby="demo-title">
        <div className="demo-panel">
          <div className="demo-copy">
            <div className="section-index">04 / HEAR IT FIRST</div>
            <p className="kicker">NO PERSONAL STEMS NEEDED.</p>
            <h2 id="demo-title">Start with your ears.</h2>
            <p>
              Run the built-in synthetic demo to see the actual automatic
              MIDI/WAV/ZIP path. Then hear “Out of Place” for the wider creative
              goal: musical ideas carried into a new MIDI-derived interpretation.
            </p>
            <div className="hero-actions">
              <ExternalLink className="button button-hot" href={links.outOfPlace}>
                <span className="play-mark" aria-hidden="true">▶</span>
                Listen on SoundCloud
              </ExternalLink>
              <Link className="button button-ghost" href="/demo">
                Get the 3-step demo instructions →
              </Link>
            </div>
          </div>
          <Image
            src="/examples/out-of-place.png"
            alt="Out of Place, a Sunofriend musical interpolation"
            width={1254}
            height={1254}
            unoptimized
          />
        </div>
      </section>

      <section className="boundary section-shell" aria-labelledby="boundary-title">
        <div>
          <span className="card-number">CURRENT BOUNDARY</span>
          <h2 id="boundary-title">Local alpha, honestly labelled.</h2>
        </div>
        <div className="boundary-list">
          <p>
            <strong>It is not an online converter.</strong> This website never
            receives your stems. Processing currently happens on your Mac.
          </p>
          <p>
            <strong>It is not a stem separator.</strong> Bring top-level WAV stems
            from your own project or an authorised third-party service.
          </p>
          <p>
            <strong>It is not a perfect transcription.</strong> The WAV is a
            creative MIDI interpretation, not waveform reconstruction or a
            human-approved release master.
          </p>
        </div>
      </section>

      <section className="signal section-shell" aria-labelledby="signal-title">
        <div className="section-index">05 / HELP SHAPE THE NEXT VERSION</div>
        <div className="signal-grid">
          <div>
            <p className="kicker">MADE A FIRST SONG?</p>
            <h2 id="signal-title">Tell us where it was easy and where it hurt.</h2>
          </div>
          <div className="feedback-actions">
            <ExternalLink className="button button-hot" href={links.firstSong}>
              Send a first-song report ↗
            </ExternalLink>
            <ExternalLink className="button button-ghost" href={links.compatibility}>
              Report another DAW or AI setup ↗
            </ExternalLink>
          </div>
        </div>
      </section>

      <footer>
        <div className="footer-brand">
          <Image
            src="/brand/sunofriend-logo.png"
            alt=""
            aria-hidden="true"
            width={1254}
            height={1254}
            unoptimized
          />
          <div>
            <strong>SUNOFRIEND</strong>
            <span>LISTEN DEEPER. CREATE FURTHER.</span>
          </div>
        </div>
        <div className="footer-links">
          <Link href="/for-agents">For AI agents</Link>
          <a href="/llms.txt">llms.txt</a>
          <ExternalLink href={links.repo}>GitHub ↗</ExternalLink>
          <ExternalLink href={links.license}>Apache 2.0 ↗</ExternalLink>
        </div>
        <p className="footer-note">
          <span>
            © 2026 <strong>Unsigned Media Ltd</strong> · Company No. 17046305
          </span>
          <span>
            Sunofriend takes its name from Hindi <strong>सुनो</strong>, “listen.”
            It is not related to or affiliated with Suno Inc.
          </span>
          <span>
            References to Suno, Moises, Apple, GarageBand or SoundCloud describe
            independent third-party products or examples only.
          </span>
        </p>
      </footer>
    </main>
  );
}
