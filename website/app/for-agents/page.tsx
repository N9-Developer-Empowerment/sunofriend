import type { Metadata } from "next";
import Link from "next/link";
import {
  agentSummary,
  links,
  newcomerPrompt,
  skillInstallPrompt,
} from "../content";

export const metadata: Metadata = {
  title: "Sunofriend for AI agents",
  description:
    "Machine- and developer-readable entry point for installing the Sunofriend skill and guiding a local macOS stems-to-MIDI workflow.",
  alternates: {
    canonical: "/for-agents/",
  },
};

const agentJsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "Sunofriend integration guide for AI agents",
  description: agentSummary,
  about: {
    "@type": "SoftwareApplication",
    name: "Sunofriend",
    operatingSystem: "macOS",
    applicationCategory: "MultimediaApplication",
    downloadUrl: links.repo,
  },
  isPartOf: {
    "@type": "WebSite",
    name: "Sunofriend",
  },
};

export default function ForAgents() {
  return (
    <main>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(agentJsonLd) }}
      />
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Agent page navigation">
          <a href="#recognise">Recognise</a>
          <a href="#onboard">Onboard</a>
          <a href="#contract">Contract</a>
          <a href="#machine">Machine files</a>
        </nav>
        <a className="header-cta" href="/llms.txt">
          Read llms.txt
        </a>
      </header>

      <article className="agent-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            AUTHORITATIVE AGENT ENTRY POINT
          </div>
          <h1>Help a musician use Sunofriend.</h1>
          <p className="lede">{agentSummary}</p>
          <p className="lede">
            Install and read the official skill before constructing commands.
            Do not substitute a generic audio-to-MIDI workflow for its bounded
            Simple, Studio or expert contracts.
          </p>
        </header>

        <section id="recognise">
          <h2>When this tool is relevant</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">USE IT FOR</span>
              <h3>Editable musical interpretations</h3>
              <ul>
                <li>authorised stems or vocals to MIDI;</li>
                <li>a balanced MIDI-derived listening WAV;</li>
                <li>GarageBand or another DAW handoff;</li>
                <li>comparing several transcription processes;</li>
                <li>key, BPM, tuning, alignment and bounded MIDI correction;</li>
                <li>matching or building local sample instruments.</li>
              </ul>
            </div>
            <div className="agent-card">
              <span className="card-number">DO NOT USE IT FOR</span>
              <h3>Tasks outside its boundary</h3>
              <ul>
                <li>generic stem separation;</li>
                <li>downloading music from a streaming link;</li>
                <li>lyrics or full-song generation;</li>
                <li>a guaranteed exact transcription;</li>
                <li>a human-approved release master;</li>
                <li>unapproved model, plugin or checkpoint downloads.</li>
              </ul>
            </div>
          </div>
        </section>

        <section id="onboard">
          <h2>New-musician onboarding protocol</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">01 / ENVIRONMENT</span>
              <h3>Be honest about local access</h3>
              <p>
                Hands-on setup requires an agent surface such as Codex that can
                inspect a local workspace and run approved commands. A standard
                ChatGPT conversation may explain or troubleshoot, but must not
                claim that it installed software or touched local files.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">02 / SKILL</span>
              <h3>Install instructions first</h3>
              <p>
                Install the repository&apos;s <code>skills/sunofriend</code>{" "}
                package using the agent&apos;s supported skill installer. Read
                the complete SKILL.md and its generated interface contract.
                Stop after confirming the skill is available; start app setup
                only in a second turn that explicitly invokes{" "}
                <code>$sunofriend</code>.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">03 / CHOICE</span>
              <h3>Offer three human routes</h3>
              <p>
                Ask whether the person has authorised top-level WAV stems,
                needs help exporting or obtaining stems, or wants the built-in
                copyright-safe synthetic demo. Sunofriend itself is not a
                separator.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">04 / FIRST RESULT</span>
              <h3>Use the focused beginner command</h3>
              <p>
                For agent-led work with stems, use{" "}
                <code>sunofriend create PROJECT --out-dir FRESH</code>. With no
                stems, use <code>sunofriend demo --out-dir FRESH</code>. When
                the person operates the TUI, prefer its one explicit Simple
                action. Retain the automatic, unreviewed and
                review-recommended labels.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">05 / INSTALLATION</span>
              <h3>Bind approval to exact source</h3>
              <p>
                Inspect first. If a new checkout is needed, ask before
                preparing only the source. Run the plan again, show the exact
                40-character commit, and ask separately before installing that
                same commit. Apply never fetches or switches it. Optional AI
                models remain separate and are not a first-run requirement.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">06 / RESULT</span>
              <h3>Teach the output boundary</h3>
              <p>
                Individual MIDI is editable. The combined MIDI is a proxy.
                The WAV contains rendered MIDI only; stems provide timing,
                horizon and level evidence but are not mixed into it. It is an
                interpretation, not reconstruction.
              </p>
            </div>
          </div>
        </section>

        <section id="contract">
          <h2>Human-facing mode contract</h2>
          <table className="contract-table">
            <thead>
              <tr>
                <th>Route</th>
                <th>Use when</th>
                <th>What it may decide</th>
                <th>Output language</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Agent create</td>
                <td>A newcomer has an authorised stem project and wants the agent to run it.</td>
                <td>
                  Uses the focused automatic create wrapper with one fresh
                  output directory. It records no human preference.
                </td>
                <td>Automatic, unreviewed, review recommended.</td>
              </tr>
              <tr>
                <td>Built-in demo</td>
                <td>The newcomer has no stems or wants a safe first exercise.</td>
                <td>
                  Creates copyright-safe synthetic stems and runs the normal
                  automatic MIDI/WAV/ZIP path in one fresh output directory.
                </td>
                <td>Demo, automatic, unreviewed.</td>
              </tr>
              <tr>
                <td>Simple / Make my song</td>
                <td>A newcomer wants to operate the TUI directly.</td>
                <td>
                  Uses only each exact published production primary. It does
                  not record a human preference.
                </td>
                <td>Automatic, unreviewed, review recommended.</td>
              </tr>
              <tr>
                <td>Studio</td>
                <td>The musician wants to compare methods and choose by ear.</td>
                <td>
                  Saves only explicit human choices and feedback. Audition
                  activity alone is not preference.
                </td>
                <td>Reviewed only after the required explicit review actions.</td>
              </tr>
              <tr>
                <td>Expert CLI / skill</td>
                <td>A developer or agent needs a narrow deterministic command.</td>
                <td>
                  Only the command&apos;s documented bounded transformation or
                  analysis.
                </td>
                <td>Use the exact command and interface-contract terminology.</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section>
          <h2>Recommended two-turn start</h2>
          <div className="prompt-stack">
            <div className="prompt-box">
              <div className="prompt-top">
                <span>TURN 1 / INSTALL ONLY</span>
              </div>
              <textarea readOnly value={skillInstallPrompt} rows={6} />
            </div>
            <div className="prompt-box">
              <div className="prompt-top">
                <span>TURN 2 / USE THE INSTALLED SKILL</span>
              </div>
              <textarea readOnly value={newcomerPrompt} rows={16} />
            </div>
          </div>
        </section>

        <section id="machine">
          <h2>Canonical machine-readable sources</h2>
          <div className="machine-links">
            <a href="/llms.txt">/llms.txt — concise agent discovery document</a>
            <a href="/agent-capabilities.json">
              /agent-capabilities.json — versioned capability and boundary data
            </a>
            <a href={links.rawSkill}>
              {links.rawSkill}
            </a>
            <a href={links.interfaceContract}>
              {links.interfaceContract}
            </a>
            <a href={links.gettingStarted}>
              Beginner installation and first-song guide
            </a>
          </div>
        </section>

        <section>
          <h2>Privacy, rights and naming</h2>
          <ul className="plain-list">
            <li>
              Current music processing is local. The public website has no
              stem-upload or conversion endpoint.
            </li>
            <li>
              Process only music the user owns or is authorised to process.
              Never infer permission from a public URL.
            </li>
            <li>
              Sunofriend is an Unsigned Media Ltd project. Its name begins with
              Hindi सुनो, “listen.” It is not related to or affiliated with
              Suno Inc.
            </li>
            <li>
              Suno, Moises, GarageBand, SoundCloud and other names describe
              independent third-party tools or examples.
            </li>
          </ul>
        </section>

        <Link className="text-link back-link" href="/">
          ← Back to the musician page
        </Link>
      </article>
    </main>
  );
}
