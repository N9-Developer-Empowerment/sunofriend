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
    "Experimental local separation into broad vocals and complementary instrumental",
    "Authorised separated audio parts to canonical WAV stems and editable MIDI",
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
          <a href="#agent">Start</a>
          <a href="#choose">Choose a route</a>
          <Link href="/stems/">What are stems?</Link>
          <Link href="/windows/">Windows notes</Link>
          <Link href="/research/separation/">Stem research</Link>
          <Link href="/research/vocal-comping/">Vocal comping</Link>
          <a href="#demo">Try the demo</a>
          <Link href="/for-agents">For AI agents</Link>
        </nav>
        <a className="header-cta" href="#agent">
          Use with your agent <span aria-hidden="true">↓</span>
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
          <p className="hero-proof">Let your agent guide the setup.</p>
          <p className="hero-lede">
            Sunofriend listens to separate drums, bass, keys, vocals and other
            song parts. It gives you editable MIDI and a clean instrumental
            interpretation you can hear before opening your music software.
          </p>
          <div className="hero-actions">
            <a className="button button-hot" href="#agent">
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
          <Link
            className="alpha-sash"
            href="/research/separation/"
            aria-label="New public opt-in preview: try local vocals, drums, bass and grouped-other stem separation"
          >
            <span>NEW · CORE-FOUR PREVIEW</span>
            <strong>VOCALS · DRUMS · BASS · OTHER</strong>
            <b>LOCAL OPT-IN SEPARATION →</b>
          </Link>
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
        <strong>macOS supported; Windows trial documented.</strong>
        <span>
          The skill should work with any coding agent that understands skills
          and can use a local workspace. Windows installation and diagnostics
          passed, but demo/create are blocked by POSIX-only locking. Read the{" "}
          <Link href="/windows/">Windows setup notes</Link>. Linux is unverified.
        </span>
      </div>

      <section id="agent" className="codex-start section-shell" aria-labelledby="agent-title">
        <div className="section-index">01 / EASIEST WAY IN</div>
        <div className="section-heading-row">
          <div>
            <p className="kicker">ONE SKILL. YOUR CHOICE OF AGENT.</p>
            <h2 id="agent-title">Give this job to your agent.</h2>
          </div>
          <p>
            The plain-text Sunofriend skill tells a compatible local agent what
            the tool can do, what must stay local and which questions to ask
            before it changes anything on your computer.
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
              <strong>Do not clone the repository first.</strong> These
              copy-ready prompts use Codex syntax. Example skills-aware agents
              include Codex, Claude Code and Antigravity. If{" "}
              <code>$sunofriend</code> is not recognised after turn 1, restart
              Codex once and send turn 2 again. In Claude Code, Antigravity or
              another agent, use its native skill installer or ask it to read
              the complete <a href={links.rawSkill}>SKILL.md</a> first.
            </p>
          </div>
          <aside className="what-happens">
            <span className="card-number">WHAT HAPPENS NEXT</span>
            <ol>
              <li>
                <strong>First turn: install only the skill.</strong>
                <span>
                  The agent confirms the guide is available, then stops before
                  installing the app or audio dependencies. The installer
                  command can differ between agents.
                </span>
              </li>
              <li>
                <strong>Second turn: explicitly use the skill.</strong>
                <span>
                  Codex can invoke <code>$sunofriend</code>; other agents can
                  follow the installed SKILL.md in their native way. The skill
                  checks the host, explains missing software and asks before
                  making changes.
                </span>
              </li>
              <li>
                <strong>You choose your starting point.</strong>
                <span>
                  Separate an authorised finished song experimentally, use
                  existing stems, get help finding stems or run the demo.
                </span>
              </li>
              <li>
                <strong>The beginner route makes a first result.</strong>
                <span>
                  Your agent can use the focused create or demo command; the TUI
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
            After installing and invoking the skill, your agent should offer
            these same four routes one at a time.
          </p>
        </div>
        <div className="journey-grid">
          <article id="separate-song" className="journey-card journey-primary">
            <span className="card-number">A / I HAVE A FINISHED SONG</span>
            <h3>I want Sunofriend to estimate stems locally.</h3>
            <p>
              On a supported Apple-silicon Mac, the public alpha estimates broad
              vocals and complementary instrumental by default. Its explicit
              SCNet core-four opt-in estimates vocals, drums, bass and grouped
              other. You listen before deciding whether any stem is useful.
            </p>
            <ul>
              <li>Audio stays on your Mac</li>
              <li>Separate model and runtime approval required</li>
              <li>Two broad stems by default; four grouped roles by explicit opt-in</li>
              <li>Experimental output is unreviewed</li>
            </ul>
            <Link className="text-link" href="/research/separation/">
              See setup, limits and feedback →
            </Link>
          </article>

          <article id="have-stems" className="journey-card">
            <span className="card-number">B / I HAVE STEMS</span>
            <h3>I already have separate audio files.</h3>
            <p>
              Give your agent the folder location. It will check the files and,
              when needed, prepare supported WAV, AIFF, FLAC, M4A, MP3 or Ogg
              parts as one canonical WAV project before making a fresh result.
            </p>
            <ul>
              <li>Best when you already export separate parts</li>
              <li>Use music you own or can process</li>
              <li>Preparation never separates or repairs alignment</li>
              <li>Your agent then uses the focused create command</li>
            </ul>
            <a className="text-link" href="#agent">
              Copy the starter prompt ↑
            </a>
          </article>

          <article id="need-stems" className="journey-card">
            <span className="card-number">C / I NEED OTHER STEM OPTIONS</span>
            <h3>I want a DAW export or an independent service.</h3>
            <p>
              A stem is a synchronized grouped part, not necessarily one
              instrument. The guide explains DAW exports and independent local
              or cloud options when the local experimental profiles are not suitable.
            </p>
            <div className="journey-links">
              <Link className="text-link" href="/stems/">
                What stems are and where to get them →
              </Link>
              <Link className="text-link text-link-muted" href="/glossary/">
                Open the glossary →
              </Link>
            </div>
            <small>
              Local and cloud tools have different privacy boundaries. Never
              upload or process music unless you have the necessary rights.
            </small>
          </article>

          <article id="want-demo" className="journey-card">
            <span className="card-number">D / I WANT THE DEMO</span>
            <h3>I want to try it without personal music or paid stems.</h3>
            <p>
              Let your agent run a copyright-safe synthetic stem project
              through the real automatic pipeline. Then hear the result and
              explore the included worked MIDI pack.
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

      <section className="vocal-lab section-shell" aria-labelledby="vocal-lab-title">
        <div className="section-index">05 / IN THE LAB</div>
        <div className="vocal-lab-grid">
          <div>
            <p className="kicker">KEEP YOUR VOICE. BUILD THE PERFORMANCE.</p>
            <h2 id="vocal-lab-title">Vocal comping is taking shape.</h2>
            <p>
              Sunofriend is exploring a local browser workflow for recording
              several attempts, comparing complete musical phrases and asking
              for focused pickups until your own vocal is ready to assemble.
              Known lyrics and a reviewed melody guide the process; your ears
              still make every musical choice.
            </p>
            <Link className="button button-hot" href="/research/vocal-comping/">
              See the pilot and whole-song concept →
            </Link>
          </div>
          <div className="vocal-lab-status" aria-label="Current vocal comping research status">
            <article>
              <span>WORKING PRIVATELY</span>
              <strong>Phrase recording + aligned pickups</strong>
            </article>
            <article>
              <span>WORKING PRIVATELY</span>
              <strong>Listening-first take comparison</strong>
            </article>
            <article>
              <span>DESIGNING NEXT</span>
              <strong>Whole-song map + natural assembly</strong>
            </article>
            <article>
              <span>NOT IMPLEMENTED</span>
              <strong>Automatic selection, joins or tuning</strong>
            </article>
          </div>
        </div>
        <p className="guide-note">
          This is a private research pilot, not a public recording service. The
          website cannot receive audio, and no automatic finished vocal comp is
          available yet.
        </p>
      </section>

      <section className="boundary section-shell" aria-labelledby="boundary-title">
        <div>
          <span className="card-number">CURRENT BOUNDARY</span>
          <h2 id="boundary-title">Local alpha, honestly labelled.</h2>
        </div>
        <div className="boundary-list">
          <p>
            <strong>It is not an online converter.</strong> This website never
            receives your stems. Processing is local. macOS is the supported
            route; native Windows setup and diagnostics are partially verified,
            but the normal demo/create path is currently blocked by POSIX-only
            locking. <Link className="inline-link" href="/windows/">Read the
            Windows trial notes</Link>. Linux remains unverified.
          </p>
          <p>
            <strong>It is not a one-click multitrack recovery service.</strong>{" "}
            The public local alpha defaults to broad vocals plus complementary
            instrumental on a supported Apple-silicon Mac. An exact core-four
            MLX profile and its first PyTorch fallback are implemented but remain
            fail-closed after their bounded objective remediations failed. A
            hash-pinned SCNet-large release profile is now available as an
            explicit public opt-in preview for vocals, drums, bass and grouped
            other after its finite offline canaries and catastrophic-output
            listening checks passed. Separate private, unregistered six-role
            research combined core four with synth and guitar specialists. Its
            completed three-song review found all 3/3 cases useful and
            non-catastrophic; synth and guitar were each useful in 2/2
            confirmed-present cases, with some missing content reported for both.
            This is positive private evidence only: resource and objective
            qualification remain incomplete, and there is no public six-role
            command, profile registration, automatic source choice or activation.
            Bring original or authorised parts when you need reliable keys,
            guitars or narrower families. See the{" "}
            <Link className="inline-link" href="/stems/">
              neutral stems guide
            </Link>
            .
          </p>
          <p>
            <strong>The working two-stem slice remains the public default.</strong>{" "}
            Core four is explicit opt-in. Both keep setup, rights
            confirmation, local inference, listening and later MIDI conversion
            as separate steps. Read the{" "}
            <Link className="inline-link" href="/research/separation/">
              setup, limits, evidence and feedback guide
            </Link>
            .
          </p>
          <p>
            <strong>It is not a perfect transcription.</strong> The WAV is a
            creative MIDI interpretation, not waveform reconstruction or a
            human-approved release master.
          </p>
        </div>
      </section>

      <section className="signal section-shell" aria-labelledby="signal-title">
        <div className="section-index">06 / HELP SHAPE THE NEXT VERSION</div>
        <div className="signal-grid">
          <div>
            <p className="kicker">YOUR EXPERIENCE CAN IMPROVE THE NEXT VERSION.</p>
            <h2 id="signal-title">Tell us what worked—and what did not.</h2>
            <p>
              Feedback from every Sunofriend user is welcome. Reports from
              Claude Code, Antigravity or another skills-aware agent are
              especially useful, as are follow-up Windows and Linux trials that
              could help make SKILL.md and the setup path more portable.
            </p>
          </div>
          <div className="feedback-actions">
            <ExternalLink className="button button-hot" href={links.firstSong}>
              Send a first-song report ↗
            </ExternalLink>
            <ExternalLink className="button button-ghost" href={links.compatibility}>
              Send compatibility feedback ↗
            </ExternalLink>
            <Link className="text-link" href="/research/separation/">
              Follow stem-separation research →
            </Link>
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
          <Link href="/contact/">Contact</Link>
          <Link href="/privacy/">Privacy</Link>
          <Link href="/stems/">Stems guide</Link>
          <Link href="/glossary/">Glossary</Link>
          <Link href="/demo/">Demo</Link>
          <Link href="/windows/">Windows setup</Link>
          <Link href="/for-agents">For AI agents</Link>
          <Link href="/research/separation/">Separation research</Link>
          <Link href="/research/vocal-comping/">Vocal comping research</Link>
          <a href="/llms.txt">llms.txt</a>
          <ExternalLink href={links.repo}>GitHub ↗</ExternalLink>
          <ExternalLink href={links.license}>Apache 2.0 ↗</ExternalLink>
          <a href={links.email}>hello@sunofriend.com</a>
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
