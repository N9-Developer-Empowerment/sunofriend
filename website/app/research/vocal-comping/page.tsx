import type { Metadata } from "next";
import Link from "next/link";
import { links } from "../../content";

const title = "Vocal comping research";
const description =
  "Follow Sunofriend's private, local-first research into phrase-by-phrase recording, human-reviewed take comparison and natural whole-song vocal assembly—now planned as an audio-native workflow.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/research/vocal-comping/" },
  openGraph: {
    title: `${title} — Sunofriend`,
    description,
    url: "/research/vocal-comping/",
    images: [],
  },
  twitter: {
    card: "summary",
    title: `${title} — Sunofriend`,
    description,
    images: [],
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

const recordingRoutes = [
  {
    label: "OPTION A · MOST GUIDED",
    title: "Phrase-by-phrase recording",
    body: "Hear one reviewed phrase, record several relaxed attempts, choose a benchmark and repeat only where needed.",
    fit: "Lowest stress and clearest feedback; slower for an entire song.",
  },
  {
    label: "OPTION B · MOST CONTINUOUS",
    title: "Complete takes, then repair gaps",
    body: "Start from several full-song performances so breaths, tone and emotion carry naturally across lines.",
    fit: "Fast when a complete take is already close; harder when range or confidence varies sharply.",
  },
  {
    label: "RECOMMENDED · HYBRID",
    title: "One base pass plus guided pickups",
    body: "Keep the continuity of the best broad performance, then use the browser to replace only phrases that need another attempt.",
    fit: "Balances natural flow, manageable recording and a realistic path to finishing a whole song.",
  },
] as const;

const workflow = [
  ["01", "Map", "Confirm lyrics, phrase boundaries and the intended melody before scoring any take."],
  ["02", "Record", "Loop a phrase with backing, melody or AI-reference cues; save every dry attempt at song zero."],
  ["03", "Compare", "Listen first, then reveal pitch, timing and signal evidence as supporting information."],
  ["04", "Choose", "Lock a human base for the phrase—or explicitly request another pickup or retain the AI voice."],
  ["05", "Join", "Preview transitions with breaths and handles preserved; reject any audible seam."],
  ["06", "Polish", "Optionally audition gentle correction on chosen regions only, then export a reviewed dry vocal stem."],
] as const;

export default function VocalCompingResearch() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Vocal comping research navigation">
          <a href="#status">Status</a>
          <a href="#options">Recording options</a>
          <a href="#workspace">Whole-song workspace</a>
          <a href="#workflow">Workflow</a>
          <a href="#boundaries">Boundaries</a>
        </nav>
        <ExternalLink className="header-cta" href={links.repo}>
          View the code ↗
        </ExternalLink>
      </header>

      <article className="agent-page vocal-research-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            PRIVATE RESEARCH PILOT · NOT A FINISHED PRODUCT
          </div>
          <h1>Keep your voice. Build the best performance.</h1>
          <p className="lede">
            Sunofriend is exploring lyric-aware, melody-aware vocal comping:
            record your own voice, compare several takes one musical phrase at
            a time, make the choices yourself, and assemble a natural dry vocal
            before considering any gentle correction.
          </p>
        </header>

        <section className="status-panel" aria-label="Direction update">
          <span className="card-number">DIRECTION UPDATE · AUGUST 2026</span>
          <h2>Now planned as audio-native: no MIDI file required.</h2>
          <p>
            Target MIDI is no longer the canonical or required representation
            for vocal comping. The{" "}
            <ExternalLink className="text-link" href={links.semanticStatePlan}>
              Semantic Musical State programme
            </ExternalLink>{" "}
            defines the forward plan: a shared, time-aligned musical state
            supports vocal comping and identity-preserving remix together, and a
            reviewed phrase can be recorded, compared and chosen with no MIDI
            input. The pilot below is the implemented v1 record and remains
            reproducible as historical evidence.
          </p>
        </section>

        <section id="status" className="status-panel">
          <span className="card-number">WHAT EXISTS TODAY</span>
          <h2>A working phrase pilot—not automatic comping.</h2>
          <p>
            A private browser prototype can play a reviewed phrase, record
            aligned vocal-only attempts, compare them with a reviewed melody and
            collect an explicit listening decision. Local analysis can rank
            evidence, but it does not select a take, tune a note, join phrases
            or render a replacement vocal.
          </p>
          <p>
            The pilot has already exposed important design rules: supplied
            lyrics must remain canonical; speech transcription is only a rough
            phonetic clue; consonants and guttural closures are not failed pitch;
            and a singer must be able to request another relaxed pickup instead
            of accepting the highest score.
          </p>
        </section>

        <section id="options">
          <h2>Three ways to cover a whole song.</h2>
          <div className="recording-route-grid">
            {recordingRoutes.map((route) => (
              <article className="agent-card" key={route.title}>
                <span className="card-number">{route.label}</span>
                <h3>{route.title}</h3>
                <p>{route.body}</p>
                <p className="route-fit">{route.fit}</p>
              </article>
            ))}
          </div>
          <p className="guide-note">
            The proposed default is the hybrid route. It avoids a brittle
            word-by-word “Franken-vocal,” retains a broad human performance as
            the continuity anchor, and turns the browser into a focused pickup
            coach wherever that base is not good enough.
          </p>
        </section>

        <section id="workspace">
          <h2>The proposed whole-song workspace.</h2>
          <p className="lede">
            One screen should answer three questions at all times: where am I in
            the song, what am I hearing now, and what decision is still needed?
          </p>
          <div className="comp-workspace" aria-label="Concept layout for the future whole-song vocal comping interface">
            <aside className="song-map">
              <span className="workspace-label">SONG MAP · 18 PHRASES</span>
              <div className="song-progress"><span style={{ width: "44%" }} /></div>
              <ol>
                <li className="is-locked"><b>01</b><span>Reviewed base</span><em>LOCKED</em></li>
                <li className="is-locked"><b>02</b><span>Reviewed base</span><em>LOCKED</em></li>
                <li className="is-active"><b>03</b><span>Current phrase</span><em>4 TAKES</em></li>
                <li><b>04</b><span>Needs pickup</span><em>OPEN</em></li>
                <li><b>05</b><span>Boundary check</span><em>REVIEW</em></li>
                <li><b>06</b><span>Not recorded</span><em>EMPTY</em></li>
              </ol>
            </aside>

            <div className="phrase-stage">
              <div className="workspace-topline">
                <span>VERSE 1 · PHRASE 03</span>
                <span>BACKING CUE · LOOP ON</span>
              </div>
              <blockquote>“The lyric for this complete musical phrase”</blockquote>
              <div className="phrase-wave" aria-hidden="true">
                {[42, 66, 35, 74, 58, 87, 52, 69, 33, 77, 61, 46, 82, 55, 71, 38, 64, 49, 79, 44, 62, 34, 70, 50].map((height, index) => (
                  <i key={index} style={{ height: `${height}%` }} />
                ))}
              </div>
              <div className="transport-row">
                <button type="button" aria-label="Play phrase concept control">▶ PLAY</button>
                <button type="button" className="record-concept" aria-label="Record phrase concept control">● RECORD TAKE</button>
                <span>HEADPHONES ON · DRY INPUT</span>
              </div>
              <div className="take-tray">
                <button type="button"><b>TAKE 01</b><span>natural ending</span></button>
                <button type="button" className="is-auditioning"><b>TAKE 02</b><span>auditioning</span></button>
                <button type="button"><b>TAKE 03</b><span>late entrance</span></button>
                <button type="button"><b>TAKE 04</b><span>strong pitch</span></button>
              </div>
            </div>

            <aside className="decision-panel">
              <span className="workspace-label">HUMAN DECISION</span>
              <h3>What should happen here?</h3>
              <button type="button" className="decision-primary">USE AS PHRASE BASE</button>
              <button type="button">KEEP AS BENCHMARK</button>
              <button type="button">RECORD ANOTHER PICKUP</button>
              <button type="button">KEEP AI FOR NOW</button>
              <details>
                <summary>Reveal analysis after listening</summary>
                <p>Pitch, timing, coverage and signal evidence—never an automatic choice.</p>
              </details>
            </aside>
          </div>
          <p className="concept-caption">
            Concept only. These controls illustrate the intended interaction;
            the public website does not record, upload or process audio.
          </p>
        </section>

        <section id="workflow">
          <h2>From first phrase to export.</h2>
          <div className="workflow-grid">
            {workflow.map(([number, name, explanation]) => (
              <article className="workflow-step" key={number}>
                <span>{number}</span>
                <h3>{name}</h3>
                <p>{explanation}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="boundaries">
          <h2>What the design must protect.</h2>
          <ul className="check-list">
            <li><strong>Your audio stays local.</strong> The public site has no upload or hosted vocal-processing endpoint.</li>
            <li><strong>Listening outranks scoring.</strong> Automated evidence stays collapsed until the singer has heard the alternatives.</li>
            <li><strong>The unit is usually a phrase.</strong> Word or syllable substitutions are rescue tools only after safe boundaries are reviewed.</li>
            <li><strong>One broad base preserves identity.</strong> Switch penalties, breath handles, timbre and expression continuity matter as much as pitch.</li>
            <li><strong>No acceptable take is a valid result.</strong> The interface asks for another pickup instead of hiding the gap with correction.</li>
            <li><strong>Correction is optional and downstream.</strong> It may be auditioned gently on chosen audio only; originals and uncorrected renders remain intact.</li>
            <li><strong>AI remains visibly separate.</strong> An authorised AI reference or duet region is a labelled fallback, never silently presented as the singer.</li>
          </ul>
        </section>

        <section className="status-panel">
          <span className="card-number">NEXT RESEARCH INCREMENT</span>
          <h2>Go audio-native, then earn assembly.</h2>
          <p>
            The next useful step is the programme's Cycle 1: a minimum no-MIDI
            phrase decision with an exact source map, one or more fresh browser
            pickups and a playable replacement phrase against the backing—then
            the musical and workflow feedback, before adding analysis. In
            parallel, the first label snapshot is frozen and tiny local training
            experiments prove the pipeline; every trained output stays a
            research challenger that can never select a take.
          </p>
          <p>
            Whole-song assembly, reviewed joins and gentle correction follow
            only after that audio-native loop is comfortable across complete
            songs. See the{" "}
            <ExternalLink className="text-link" href={links.semanticStatePlan}>
              canonical programme plan ↗
            </ExternalLink>{" "}
            and the{" "}
            <Link className="text-link" href="/research/remixing/">
              remix research plan
            </Link>
            .
          </p>
        </section>

        <Link className="text-link back-link" href="/">
          ← Back to Sunofriend
        </Link>
      </article>
    </main>
  );
}
