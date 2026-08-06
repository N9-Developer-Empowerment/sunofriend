import type { Metadata } from "next";
import Link from "next/link";
import { links, separationResearch } from "../../content";

export const metadata: Metadata = {
  title: "Stem separation research — Sunofriend",
  description:
    "Public status and feedback boundary for Sunofriend's private local stem-separation research.",
  alternates: { canonical: "/research/separation/" },
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

export default function SeparationResearch() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Separation research navigation">
          <a href="#working">What works</a>
          <a href="#boundary">Current boundary</a>
          <a href="#feedback">Give feedback</a>
          <Link href="/stems/">Stem guide</Link>
        </nav>
        <Link className="header-cta" href="/demo/">
          Try the public demo
        </Link>
      </header>

      <article className="agent-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            PUBLIC RESEARCH STATUS · PRIVATE AUDIO
          </div>
          <h1>We are testing local stem separation in the open.</h1>
          <p className="lede">
            The evidence, limits and next questions are public so musicians and
            developers can challenge the direction. The audio, model files and
            listening notes remain private on the tester&apos;s Mac.
          </p>
        </header>

        <section id="working">
          <h2>What now works in private development</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">BOUNDED WORKING SCOPE</span>
              <h3>Finished mix to two broad stems</h3>
              <p>{separationResearch.workingPrivateScope}.</p>
              <p>
                The broad instrumental is not individual bass, keys, drums or
                guitar. The reconstruction is a diagnostic integrity check, not
                a stem for normal use.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">DOWNSTREAM PROOF</span>
              <h3>Separation can feed the useful Sunofriend workflow</h3>
              <p>{separationResearch.downstreamProof}.</p>
              <p>
                That output is still automatic and unreviewed. It is a musical
                interpretation, not an exact reconstruction or release master.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">EVIDENCE</span>
              <h3>Whole songs, joins and repeatable execution</h3>
              <p>{separationResearch.evidenceScope}.</p>
              <p>
                Reviews preserve clean, audible and uncertain outcomes. A join
                can be measurable yet musically acceptable, so microscopic
                diagnostics do not automatically veto a useful private result.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">HUMAN BOUNDARY</span>
              <h3>Software checks evidence; people judge music</h3>
              <p>{separationResearch.humanAuthority}.</p>
              <p>
                Playback activity never becomes a preference. A result advances
                only after an explicit, result-bound listening review.
              </p>
            </div>
          </div>
        </section>

        <section id="boundary">
          <h2>Why it is not a public separator yet</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">STATUS</span>
              <h3>{separationResearch.status}</h3>
              <p>
                There is no separation button in Simple, Studio, the public
                CLI, the website or the beginner skill journey. Sunofriend does
                not upload audio and does not redistribute the private model.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">OPEN GATES</span>
              <h3>Useful research is not the same as a supported feature</h3>
              <ul>
                {separationResearch.openGates.map((gate) => (
                  <li key={gate}>{gate};</li>
                ))}
              </ul>
            </div>
          </div>
          <p className="guide-note">
            The current public Sunofriend route still starts with authorised,
            already-separated parts. See the <Link href="/stems/">stem guide</Link>{" "}
            or use the copyright-safe <Link href="/demo/">built-in demo</Link>.
          </p>
        </section>

        <section id="feedback">
          <h2>Help improve the next public slice</h2>
          <p className="lede">{separationResearch.feedbackBoundary}</p>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">MUSICIANS</span>
              <h3>Try the current stems-to-MIDI product</h3>
              <p>
                Tell us whether setup was understandable, which stem provider
                you used, which MIDI parts were useful and whether the balanced
                interpretation helped you hear the song differently.
              </p>
              <ExternalLink className="text-link" href={links.firstSong}>
                Send a first-song report ↗
              </ExternalLink>
            </div>
            <div className="agent-card">
              <span className="card-number">DEVELOPERS AND TESTERS</span>
              <h3>Challenge the feature boundary</h3>
              <p>
                Report operating system, hardware, agent, DAW, separator,
                source format, exact command and the first confusing or failing
                step. Describe audible behaviour without uploading private
                music.
              </p>
              <ExternalLink className="text-link" href={links.compatibility}>
                Send compatibility feedback ↗
              </ExternalLink>
            </div>
          </div>
        </section>

        <Link className="text-link back-link" href="/">
          ← Back to the musician page
        </Link>
      </article>
    </main>
  );
}
