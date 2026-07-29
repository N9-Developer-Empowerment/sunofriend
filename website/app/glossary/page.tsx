import type { Metadata } from "next";
import Link from "next/link";
import { glossaryEntries } from "../content";

export const metadata: Metadata = {
  title: "Music stems and MIDI glossary",
  description:
    "Plain-language definitions for stems, multitracks, AI-separated audio, leakage, residuals, MIDI and sample instruments.",
  alternates: {
    canonical: "/glossary/",
  },
};

export default function Glossary() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Glossary navigation">
          <Link href="/stems/">Get stems</Link>
          <Link href="/demo/">Try the demo</Link>
          <Link href="/for-agents/">For AI agents</Link>
        </nav>
        <Link className="header-cta" href="/#codex">
          Use the skill
        </Link>
      </header>

      <article className="agent-page guide-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            PLAIN-LANGUAGE MUSIC GLOSSARY
          </div>
          <h1>From audio parts to editable notes.</h1>
          <p className="lede">
            The words around separation and MIDI can be confusing. These
            definitions describe how Sunofriend uses them.
          </p>
          <div className="hero-actions">
            <Link className="button button-hot" href="/stems/">
              Where to get stems
            </Link>
            <Link className="button button-ghost" href="/demo/">
              Try without personal music
            </Link>
          </div>
        </header>

        <section aria-labelledby="terms-title">
          <h2 id="terms-title">The essential terms</h2>
          <dl className="glossary-grid">
            {glossaryEntries.map((entry) => (
              <div className="glossary-entry" key={entry.term}>
                <dt>{entry.term}</dt>
                <dd>
                  <strong>{entry.short}</strong>
                  <span>{entry.explanation}</span>
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="status-panel" aria-labelledby="remember-title">
          <span className="card-number">THE ONE THING TO REMEMBER</span>
          <h2 id="remember-title">A stem can contain many sounds.</h2>
          <p>
            The filename describes a useful category, not proof that one
            instrument is isolated. Listen to the source, inspect any leakage
            and treat AI separation as an estimate before judging its MIDI.
          </p>
        </section>

        <div className="journey-links back-link">
          <Link className="text-link" href="/">
            ← Back to Sunofriend
          </Link>
          <Link className="text-link text-link-muted" href="/stems/">
            Read the stems guide →
          </Link>
        </div>
      </article>
    </main>
  );
}
