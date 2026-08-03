import type { Metadata } from "next";
import Link from "next/link";
import { CopyPrompt } from "../copy-prompt";
import { demoPrompt, links, skillInstallPrompt } from "../content";

export const metadata: Metadata = {
  title: "Sunofriend built-in demo",
  description:
    "Run Sunofriend's copyright-safe synthetic stem demo, hear its automatic MIDI/WAV result and explore a public worked MIDI pack.",
  alternates: {
    canonical: "/demo/",
  },
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

export default function Demo() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Demo navigation">
          <a href="#run">Run</a>
          <a href="#hear">Hear</a>
          <a href="#continue">Continue</a>
          <Link href="/glossary/">Glossary</Link>
        </nav>
        <Link className="header-cta" href="/stems/">
          What are stems?
        </Link>
      </header>

      <article className="agent-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            COPYRIGHT-SAFE BUILT-IN DEMO
          </div>
          <h1>Make a complete result without personal music.</h1>
          <p className="lede">
            Sunofriend can generate a small synthetic stem project and run it
            through the normal automatic conversion. You get the same kinds of
            MIDI, listening WAV, receipt and ZIP as a first personal project,
            clearly marked automatic and unreviewed.
          </p>
        </header>

        <section id="run">
          <h2>1. Ask a skills-aware coding agent to run it</h2>
          <div className="codex-grid">
            <div className="prompt-stack">
              <CopyPrompt
                prompt={skillInstallPrompt}
                label="TURN 1 / INSTALL THE SKILL"
              />
              <CopyPrompt prompt={demoPrompt} label="TURN 2 / RUN THE DEMO" />
              <p className="prompt-help">
                <strong>Do not clone the repository first.</strong> These
                prompts are the copy-ready Codex route. If{" "}
                <code>$sunofriend</code> is not recognised after turn 1,
                restart Codex once and send turn 2 again. Claude Code,
                Antigravity and other agents should use their native skill
                mechanism or read the complete{" "}
                <a href={links.rawSkill}>SKILL.md</a> directly.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">THE REAL DEMO COMMAND</span>
              <h3>One fresh output folder</h3>
              <p>
                The skill guides your coding agent to run{" "}
                <code>sunofriend demo --out-dir FRESH</code>. The command
                creates copyright-safe synthetic stems, then uses the normal
                automatic MIDI/WAV/ZIP pipeline. It will not overwrite an
                existing folder.
              </p>
              <ul>
                <li>no personal audio;</li>
                <li>no optional AI model required;</li>
                <li>local processing;</li>
                <li>automatic, unreviewed output.</li>
              </ul>
            </div>
          </div>
        </section>

        <section id="hear">
          <h2>2. Hear what the result means</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">YOUR DEMO OUTPUT</span>
              <h3>Play the balanced WAV first</h3>
              <p>
                Ask your agent to point out the listening WAV and start guide.
                Then inspect the individual MIDI. The synthetic sources provide
                timing, song length and level evidence; their audio is not
                mixed into the MIDI-derived WAV.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">WIDER MUSICAL EXAMPLE</span>
              <h3>Listen to “Out of Place”</h3>
              <p>
                This SoundCloud example shows the creative destination beyond
                the synthetic exercise: musical structure carried into a new
                MIDI-derived interpretation, not an exact copy of the source.
              </p>
              <div className="journey-links">
                <ExternalLink className="text-link" href={links.outOfPlace}>
                  Play on SoundCloud ↗
                </ExternalLink>
              </div>
            </div>
          </div>
        </section>

        <section id="continue">
          <h2>3. Inspect, then choose your next step</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">PUBLIC WORKED OUTPUT</span>
              <h3>The Aisle at Lidl MIDI pack</h3>
              <p>
                The repository also includes a small public pack with
                individual and full-arrangement Standard MIDI files plus
                provenance. Drag one into a DAW and choose your own instrument.
              </p>
              <div className="journey-links">
                <ExternalLink className="text-link" href={links.lidlPack}>
                  Open the worked pack ↗
                </ExternalLink>
                <ExternalLink className="text-link text-link-muted" href={links.lidl}>
                  Hear the finished workflow ↗
                </ExternalLink>
              </div>
            </div>
            <div className="agent-card">
              <span className="card-number">READY FOR YOUR SONG</span>
              <h3>Bring authorised top-level WAV stems</h3>
              <p>
                Return to the main prompt. Codex can use the focused{" "}
                <code>sunofriend create PROJECT --out-dir FRESH</code> route.
                If you want to operate the interface yourself, the TUI&apos;s
                Simple / Make my song mode provides the visual one-action route.
              </p>
              <div className="journey-links">
                <Link className="text-link" href="/#codex">
                  Use my stems →
                </Link>
                <Link className="text-link text-link-muted" href="/stems/">
                  Learn how to get stems →
                </Link>
              </div>
            </div>
          </div>
        </section>

        <Link className="text-link back-link" href="/">
          ← Back to Sunofriend
        </Link>
      </article>
    </main>
  );
}
