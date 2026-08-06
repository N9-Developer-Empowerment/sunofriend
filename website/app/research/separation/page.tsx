import type { Metadata } from "next";
import Link from "next/link";
import { links, separationResearch } from "../../content";

export const metadata: Metadata = {
  title: "Experimental local stem separation — Sunofriend",
  description:
    "Try Sunofriend's public local two-stem alpha, understand its limits and share text-only feedback.",
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
        <nav aria-label="Separation alpha navigation">
          <a href="#working">What works</a>
          <a href="#try">How to try it</a>
          <a href="#development">How it was built</a>
          <a href="#limits">Limits</a>
          <a href="#feedback">Give feedback</a>
          <Link href="/stems/">Stem guide</Link>
        </nav>
        <ExternalLink className="header-cta" href={links.repo}>
          View the code ↗
        </ExternalLink>
      </header>

      <article className="agent-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            PUBLIC EXPERIMENTAL ALPHA · AUDIO STAYS LOCAL
          </div>
          <h1>Try the useful slice. Help improve the next one.</h1>
          <p className="lede">
            Sunofriend can now estimate broad vocals and complementary
            instrumental from one authorised finished song on an Apple-silicon
            Mac. You hear the source, both stems and their reconstruction before
            deciding whether anything is useful.
          </p>
        </header>

        <section id="working">
          <h2>What works now</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">PUBLIC WORKING SCOPE</span>
              <h3>Finished mix to two broad stems</h3>
              <p>{separationResearch.workingPrivateScope}.</p>
              <p>
                The instrumental is the complement of the estimated vocals. It
                is not individual bass, keys, drums or guitar.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">LISTENING PACKAGE</span>
              <h3>Four local tracks make the boundary audible</h3>
              <p>
                The output includes a level-managed source reference, vocals,
                instrumental and an additive reconstruction check, plus a local
                page with review prompts and private JSON export.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">DOWNSTREAM PATH</span>
              <h3>Useful stems can continue to MIDI</h3>
              <p>{separationResearch.downstreamProof}.</p>
              <p>
                The alpha never silently activates a stem or starts MIDI
                conversion. The musician makes that later decision.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">HUMAN BOUNDARY</span>
              <h3>Software checks evidence; people judge music</h3>
              <p>{separationResearch.humanAuthority}.</p>
            </div>
          </div>
        </section>

        <section id="try">
          <h2>How to try the public alpha</h2>
          <p className="lede">
            Start with the Sunofriend skill if you want an agent to guide the
            setup. The separate model/runtime download is never part of the
            ordinary demo and requires its own approval.
          </p>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">01 · INSPECT SETUP</span>
              <h3>Plan before downloading</h3>
              <p>
                Run <code>{separationResearch.setupPlanCommand}</code>. It
                explains platform, model terms, size, network use and install
                location without changing the Mac.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">02 · VERIFY</span>
              <h3>Check the exact local profile</h3>
              <p>
                After explicit installation, run{" "}
                <code>{separationResearch.developerDoctorCommand}</code>. The
                doctor hashes the pinned files without loading the model or
                processing audio.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">03 · PLAN THE SONG</span>
              <h3>Review rights, source and output first</h3>
              <p>
                Run <code>{separationResearch.separationPlanCommand}</code> with
                an accurate rights category. Planning writes no song output.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">04 · LISTEN</span>
              <h3>Execute only after confirming authority</h3>
              <p>
                Add <code>--execute --confirm-rights --open-review</code>. The
                model runs locally with offline settings. Judge usefulness,
                bleed, missing content, texture and joins before using a stem.
              </p>
            </div>
          </div>
          <p className="guide-note">
            Read the complete{" "}
            <ExternalLink href={links.separationDeveloperGuide}>
              setup, architecture, commands and tests ↗
            </ExternalLink>
            . Sunofriend never downloads a song or supplies permission to
            process it.
          </p>
        </section>

        <section id="development">
          <h2>How the feature was developed</h2>
          <p className="lede">
            The first public slice follows a bounded evidence loop rather than
            promoting the first model that ran. Private development covered
            three source-distinct full-song chains and targeted join reviews;
            the public route then passed an end-to-end generated-audio smoke
            test with exact PCM24 geometry and reconstruction accounting.
          </p>
          <div className="agent-grid">
            {separationResearch.developmentLoop.map((step, index) => (
              <div className="agent-card" key={step}>
                <span className="card-number">
                  STEP {String(index + 1).padStart(2, "0")}
                </span>
                <h3>{step}</h3>
              </div>
            ))}
          </div>
          <p className="guide-note">
            Reports can expose a setup failure or motivate a new bounded test;
            they never silently select a model or musical default.
          </p>
        </section>

        <section id="limits">
          <h2>What remains experimental</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">STATUS</span>
              <h3>{separationResearch.status}</h3>
              <p>
                It is a separate command rather than a Simple/TUI button. It is
                verified on Apple-silicon macOS and needs roughly 500 MB for the
                pinned model plus runtime and working space.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">NOT GROUND TRUTH</span>
              <h3>Reconstruction is necessary, not sufficient</h3>
              <p>
                A close reconstruction proves additive accounting. Vocals can
                still contain accompaniment and instrumental can still contain
                vocals, holes or model artefacts.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">NEXT WORK</span>
              <h3>Public use should sharpen the roadmap</h3>
              <ul>
                {separationResearch.openGates.map((gate) => (
                  <li key={gate}>{gate};</li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section id="feedback">
          <h2>Help improve the next public slice</h2>
          <p className="lede">{separationResearch.feedbackBoundary}</p>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">MUSICIANS</span>
              <h3>Tell us whether the stems helped</h3>
              <p>
                Report whether vocals and instrumental were useful, partly
                useful or poor, and describe bleed, missing sound, metallic
                texture, level changes or joins. “Cannot tell” is useful too.
              </p>
              <ExternalLink className="text-link" href={links.firstSong}>
                Send a first-song report ↗
              </ExternalLink>
            </div>
            <div className="agent-card">
              <span className="card-number">DEVELOPERS AND TESTERS</span>
              <h3>Report the first confusing or failing step</h3>
              <p>
                Include Mac model, macOS, source format, approximate duration,
                coding agent and exact command. Do not attach private audio,
                vocals, stems or review exports.
              </p>
              <ExternalLink className="text-link" href={links.compatibility}>
                Send text-only compatibility feedback ↗
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
