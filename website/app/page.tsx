const links = {
  repo: "https://github.com/N9-Developer-Empowerment/sunofriend",
  gettingStarted:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/docs/GETTING_STARTED.md",
  outOfPlace:
    "https://soundcloud.com/ezzye-1/out-of-place?si=93616bdf10d7406c838be366106c1025&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing",
  lidl:
    "https://soundcloud.com/ezzye-1/the-aisle-at-lidl?si=97cf744ff4a743bca875bec3db88024f&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing",
  lidlPack:
    "https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/examples/the-aisle-at-lidl",
  firstSong:
    "https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=beginner-first-song.yml",
  compatibility:
    "https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml",
  license:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/LICENSE",
  brandGuide:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/BRAND.md",
  hindiName:
    "https://www.hindwi.org/hindi-dictionary/meaning-of-sunnaa-2",
  sunoTerms: "https://suno.com/terms",
};

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

export default function Home() {
  return (
    <main id="top">
      <div className="noise" aria-hidden="true" />

      <header className="site-header">
        <a className="wordmark" href="#top" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#origin">The name</a>
          <a href="#how">How it works</a>
          <a href="#examples">Hear it</a>
          <a href="#start">Try it</a>
          <a href="#signal">Send signal</a>
        </nav>
        <ExternalLink className="header-cta" href={links.repo}>
          Get the alpha <span aria-hidden="true">↗</span>
        </ExternalLink>
      </header>

      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            सुनो / SUNO = LISTEN
          </div>
          <h1 id="hero-title">
            Listen deeper.
            <span>Create further.</span>
          </h1>
          <p className="hero-proof">Your song has more than one answer.</p>
          <p className="hero-lede">
            Give Sunofriend separated stems. Get editable MIDI and a balanced
            instrumental interpretation. Hear the parts. Change the sounds.
            Make the song yours.
          </p>
          <div className="hero-actions">
            <ExternalLink className="button button-hot" href={links.outOfPlace}>
              <span className="play-mark" aria-hidden="true">
                ▶
              </span>
              Hear “Out of Place”
            </ExternalLink>
            <a className="button button-ghost" href="#start">
              Make your first song <span aria-hidden="true">↓</span>
            </a>
          </div>
          <ul className="signal-list" aria-label="Sunofriend principles">
            <li>NO UPLOAD</li>
            <li>NO BLACK-BOX WINNER</li>
            <li>INDEPENDENT BY DESIGN</li>
          </ul>
        </div>

        <div className="hero-visual">
          <div className="hero-status" aria-hidden="true">
            <span>STATUS</span>
            <strong>SIGNAL LIVE</strong>
          </div>
          <img
            src="/brand/sunofriend-listener-banner.png"
            alt="A waveform becoming the Sunofriend mark and editable MIDI notes, with सुनो meaning listen and an independence statement"
          />
          <div className="hero-stamp" aria-hidden="true">
            <span>STEMS</span>
            <b>→</b>
            <span>MIDI + WAV</span>
          </div>
        </div>
      </section>

      <div className="ticker" aria-label="Sunofriend capabilities">
        <div>
          <span>STEMS IN</span>
          <i>✦</i>
          <span>सुनो = LISTEN</span>
          <i>✦</i>
          <span>EDITABLE MIDI OUT</span>
          <i>✦</i>
          <span>SONG INTERPRETATION WAV</span>
          <i>✦</i>
          <span>LOCAL FIRST</span>
          <i>✦</i>
          <span>GARAGEBAND READY</span>
          <i>✦</i>
          <span>MORE THAN ONE ANSWER</span>
          <i>✦</i>
          <span>NOT AFFILIATED WITH SUNO INC.</span>
          <i>✦</i>
        </div>
      </div>

      <section id="origin" className="origin section-shell" aria-labelledby="origin-title">
        <div className="section-index">00 / THE NAME</div>
        <div className="origin-grid">
          <div className="origin-lead">
            <p className="kicker">LISTEN, FRIEND.</p>
            <h2 id="origin-title">
              A friend
              <span> that listens.</span>
            </h2>
          </div>
          <div className="origin-copy">
            <div className="origin-language" aria-label="Suno means listen in Hindi">
              <strong lang="hi">सुनो</strong>
              <span>SUNO / LISTEN</span>
            </div>
            <p>
              Every song begins with a simple invitation: <strong>सुनो—suno—listen.</strong>{" "}
              Sunofriend takes its name from that familiar Hindi imperative.
              Paired with “friend,” it carries two readings: “Listen, friend”
              and “a friend that listens.”
            </p>
            <p>
              That is its role. Sunofriend listens to separated musical parts,
              offers editable interpretations and hands the decisions back to
              the musician.
            </p>
            <div className="origin-independence">
              <strong>Independent, by name and by design.</strong>
              <p>
                Sunofriend is an Unsigned Media Ltd project. It is not related
                to, affiliated with, endorsed by, or sponsored by Suno Inc.,
                the AI music company.
              </p>
              <div className="origin-links">
                <ExternalLink className="text-link" href={links.hindiName}>
                  Read the Hindi meaning <span aria-hidden="true">↗</span>
                </ExternalLink>
                <ExternalLink className="text-link text-link-muted" href={links.brandGuide}>
                  Read the brand guide <span aria-hidden="true">↗</span>
                </ExternalLink>
                <ExternalLink className="text-link text-link-muted" href={links.sunoTerms}>
                  Suno trademark source <span aria-hidden="true">↗</span>
                </ExternalLink>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="manifesto section-shell" aria-labelledby="why-title">
        <div className="section-index">01 / WHY</div>
        <div className="manifesto-grid">
          <div>
            <p className="kicker">A SONG IS NOT A FLAT FILE.</p>
            <h2 id="why-title">
              Get inside it.
              <br />
              Pull it apart.
              <br />
              Build again.
            </h2>
          </div>
          <div className="manifesto-copy">
            <p>
              A finished track can sound brilliant and still be impossible to
              explore. Sunofriend turns drums, bass, keys, vocals and other
              separated parts into note interpretations you can see, hear and
              edit.
            </p>
            <p>
              Its unusual move is refusing to hide every stem behind one
              supposedly perfect answer. Simple mode gets you moving. Studio
              keeps the alternatives alive so your ears can choose.
            </p>
            <p className="pullquote">
              “The machine brings evidence. You make the musical decision.”
            </p>
          </div>
        </div>
      </section>

      <section className="benefits section-shell" aria-labelledby="benefits-title">
        <div className="section-index">02 / THE PAYOFF</div>
        <div className="section-heading-row">
          <h2 id="benefits-title">Not another magic button.</h2>
          <p>
            A playable route from generated or recorded audio to musical
            material you can actually work with.
          </p>
        </div>
        <div className="benefit-grid">
          <article className="benefit-card benefit-featured">
            <span className="card-number">A01</span>
            <h3>Editable by design</h3>
            <p>
              Move notes. Change instruments. Rework timing. Keep going in
              GarageBand or another DAW instead of being trapped inside audio.
            </p>
            <div className="piano-roll" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          </article>
          <article className="benefit-card">
            <span className="card-number">A02</span>
            <h3>Hear the whole idea</h3>
            <p>
              Sunofriend renders a balanced MIDI-only WAV so you can audition
              the interpretation before opening a full music project.
            </p>
          </article>
          <article className="benefit-card">
            <span className="card-number">A03</span>
            <h3>Local means local</h3>
            <p>
              The current app processes your stems, MIDI and private feedback
              on your Mac. There is no upload endpoint hiding in the Workbench.
            </p>
          </article>
          <article className="benefit-card">
            <span className="card-number">A04</span>
            <h3>Fast lane or deep dive</h3>
            <p>
              Simple makes an automatic, clearly unreviewed first result.
              Studio reveals comparisons, waveforms, notes and explicit
              choices.
            </p>
          </article>
          <article className="benefit-card">
            <span className="card-number">A05</span>
            <h3>Evidence stays attached</h3>
            <p>
              Source roles, timings, alternatives and receipts stay visible.
              A score can inform the work; it does not get to crown a winner.
            </p>
          </article>
        </div>
      </section>

      <section id="how" className="how section-shell" aria-labelledby="how-title">
        <div className="section-index">03 / HOW</div>
        <div className="section-heading-row">
          <h2 id="how-title">Three moves. One new version.</h2>
          <p>
            Authorised stems can come from generators or separators—including
            the independent third-party services Suno or Moises. Sunofriend
            makes them editable. Your DAW takes it from there.
          </p>
        </div>
        <ol className="steps">
          <li>
            <span className="step-number">01</span>
            <div>
              <h3>Bring the separated parts</h3>
              <p>
                Put top-level WAV stems in one folder. Name the song with its
                key, BPM and tuning. Clear role names help: kick, snare, bass,
                keys, vocals.
              </p>
              <div className="mini-path">
                MY SONG-B MINOR-113BPM-440HZ/
              </div>
            </div>
          </li>
          <li>
            <span className="step-number">02</span>
            <div>
              <h3>Hit Create MIDI + WAV</h3>
              <p>
                Launch the terminal studio, check the fresh output folder and
                let the production processes do their work. Progress stays
                visible; source files stay on the Mac.
              </p>
              <code className="inline-command">
                .venv/bin/sunofriend tui &quot;/path/to/My Song...&quot;
              </code>
            </div>
          </li>
          <li>
            <span className="step-number">03</span>
            <div>
              <h3>Listen, drag, mutate</h3>
              <p>
                Hear the balanced interpretation. Drag the individual MIDI into
                GarageBand at the exact BPM. Pick sounds, change notes and make
                the next thing.
              </p>
              <div className="output-tags">
                <span>INDIVIDUAL MIDI</span>
                <span>COMBINED MIDI</span>
                <span>BALANCED WAV</span>
                <span>STARTER ZIP</span>
              </div>
            </div>
          </li>
        </ol>
      </section>

      <section id="examples" className="examples section-shell" aria-labelledby="examples-title">
        <div className="section-index">04 / HEAR THE EVIDENCE</div>
        <div className="section-heading-row">
          <h2 id="examples-title">Press play on the idea.</h2>
          <p>
            These are musical interpretations, not attempts to impersonate
            every texture in the source.
          </p>
        </div>
        <div className="example-grid">
          <article className="example-card example-primary">
            <div className="example-art">
              <img
                src="/examples/out-of-place.png"
                alt="Out of Place, a Sunofriend interpolation"
              />
              <ExternalLink
                className="floating-play"
                href={links.outOfPlace}
              >
                <span aria-hidden="true">▶</span>
                <span className="sr-only">Play Out of Place on SoundCloud</span>
              </ExternalLink>
            </div>
            <div className="example-copy">
              <span className="example-label">LEAD EXAMPLE / INTERPOLATION</span>
              <h3>Out of Place</h3>
              <p>
                Hear musical ideas cross the gap from separated audio into a
                new MIDI-derived instrumental interpretation.
              </p>
              <ExternalLink className="text-link" href={links.outOfPlace}>
                Listen on SoundCloud <span aria-hidden="true">↗</span>
              </ExternalLink>
            </div>
          </article>
          <article className="example-card">
            <div className="example-art">
              <img
                src="/examples/the-aisle-at-lidl.png"
                alt="The Aisle at Lidl, a worked Sunofriend song"
              />
              <ExternalLink className="floating-play" href={links.lidl}>
                <span aria-hidden="true">▶</span>
                <span className="sr-only">
                  Play The Aisle at Lidl on SoundCloud
                </span>
              </ExternalLink>
            </div>
            <div className="example-copy">
              <span className="example-label">SUNO (THIRD-PARTY) → MOISES → SUNOFRIEND → DAW</span>
              <h3>The Aisle at Lidl</h3>
              <p>
                A complete four-tool workflow: AI performance, stem separation,
                timing-locked MIDI and a finished GarageBand production.
              </p>
              <div className="example-links">
                <ExternalLink className="text-link" href={links.lidl}>
                  Hear Version 1 <span aria-hidden="true">↗</span>
                </ExternalLink>
                <ExternalLink className="text-link text-link-muted" href={links.lidlPack}>
                  Explore the MIDI pack <span aria-hidden="true">↗</span>
                </ExternalLink>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section id="start" className="start section-shell" aria-labelledby="start-title">
        <div className="start-panel">
          <div className="section-index">05 / START TRANSMISSION</div>
          <div className="start-grid">
            <div>
              <p className="kicker">CURRENTLY: MACOS LOCAL ALPHA</p>
              <h2 id="start-title">Take it. Run it. Make noise.</h2>
              <p className="start-lede">
                The shortest first journey is one stem folder, one fresh output
                and one button. Installation is still a developer-style clone
                today; the beginner guide walks through it line by line.
              </p>
              <div className="hero-actions">
                <ExternalLink className="button button-hot" href={links.gettingStarted}>
                  Open the beginner guide <span aria-hidden="true">↗</span>
                </ExternalLink>
                <ExternalLink className="button button-ghost" href={links.repo}>
                  View source <span aria-hidden="true">↗</span>
                </ExternalLink>
              </div>
            </div>
            <div className="terminal-card" aria-label="Sunofriend installation commands">
              <div className="terminal-top">
                <span />
                <span />
                <span />
                <b>FIRST CONTACT</b>
              </div>
              <pre>
                <code>{`git clone https://github.com/\nN9-Developer-Empowerment/sunofriend.git\n\ncd sunofriend\nbrew install python@3.11 fluid-synth\n\n# Follow the guide, then launch:\n.venv/bin/sunofriend tui \\\n  "/path/to/your-stems"`}</code>
              </pre>
              <div className="terminal-footer">
                <span>PYTHON 3.11 RECOMMENDED</span>
                <span>APACHE-2.0</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="signal" className="signal section-shell" aria-labelledby="signal-title">
        <div className="section-index">06 / WHAT HAPPENS NEXT</div>
        <div className="signal-hero">
          <p className="kicker">THE WEB VERSION NEEDS A SIGNAL.</p>
          <h2 id="signal-title">
            If enough musicians bang on the door,
            <span> Sunofriend goes online.</span>
          </h2>
          <p>
            This launch site is serverless. The music engine is still local.
            Your feedback decides whether the next move is an invited,
            pay-per-conversion web pilot with private uploads, queued workers
            and automatic deletion.
          </p>
        </div>
        <div className="roadmap" aria-label="Sunofriend product route">
          <div className="roadmap-item roadmap-now">
            <span>NOW</span>
            <h3>Local alpha</h3>
            <p>Stems stay on your Mac. Simple and Studio are live.</p>
          </div>
          <div className="roadmap-line" aria-hidden="true" />
          <div className="roadmap-item">
            <span>NEXT</span>
            <h3>Musician proof</h3>
            <p>Clean-machine installs, more DAWs, honest first-song reports.</p>
          </div>
          <div className="roadmap-line" aria-hidden="true" />
          <div className="roadmap-item">
            <span>THEN</span>
            <h3>Hosted pilot</h3>
            <p>Short authorised songs. Private storage. Bounded cost.</p>
          </div>
        </div>
        <div className="feedback-grid">
          <article>
            <span className="card-number">F01</span>
            <h3>Made your first song?</h3>
            <p>
              Tell us whether installation worked, the WAV helped and the MIDI
              landed in your DAW at the right tempo.
            </p>
            <ExternalLink className="button button-hot" href={links.firstSong}>
              Send a first-song report <span aria-hidden="true">↗</span>
            </ExternalLink>
          </article>
          <article>
            <span className="card-number">F02</span>
            <h3>Using another setup?</h3>
            <p>
              Logic, Ableton, REAPER, FL Studio, Pro Tools, Cubase, Bitwig,
              another separator or hardware MIDI: bring it.
            </p>
            <ExternalLink className="button button-purple" href={links.compatibility}>
              Report your setup <span aria-hidden="true">↗</span>
            </ExternalLink>
          </article>
        </div>
      </section>

      <section className="truth-strip" aria-label="Current product boundary">
        <p>
          <strong>TRUTH IN THE SIGNAL:</strong> Sunofriend creates a new
          MIDI-derived interpretation. It does not promise exact waveform
          reconstruction, perfect notes or a human-approved release master.
          Use music you own or are authorised to process.
        </p>
      </section>

      <footer>
        <div className="footer-brand">
          <img src="/brand/sunofriend-logo.png" alt="" aria-hidden="true" />
          <div>
            <strong>SUNOFRIEND</strong>
            <span>LISTEN DEEPER. CREATE FURTHER.</span>
          </div>
        </div>
        <div className="footer-links">
          <ExternalLink href={links.repo}>GitHub ↗</ExternalLink>
          <ExternalLink href={links.gettingStarted}>Beginner guide ↗</ExternalLink>
          <ExternalLink href={links.license}>Apache 2.0 ↗</ExternalLink>
          <a href="#top">Back to top ↑</a>
        </div>
        <p className="footer-note">
          <span>
            © 2026 <strong>Unsigned Media Ltd</strong> · Company No. 17046305
          </span>
          <span>
            The name begins with Hindi <strong>सुनो</strong>, “listen.”
            Sunofriend is not related to or affiliated with Suno Inc.
          </span>
          <span>
            References to Suno, Moises, Apple, GarageBand, SoundCloud or Lidl
            describe independent third-party products or examples only.
          </span>
        </p>
      </footer>
    </main>
  );
}
