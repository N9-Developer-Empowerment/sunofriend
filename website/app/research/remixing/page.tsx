import type { Metadata } from "next";
import Link from "next/link";
import { links } from "../../content";

const title = "Remix research";
const description =
  "Follow Sunofriend's private, local-first research plan for bounded, editable remixes: change one instrument, role or region while keeping the musical relationships you recognise from the source.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/research/remixing/" },
  openGraph: {
    title: `${title} — Sunofriend`,
    description,
    url: "/research/remixing/",
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

const identityAnchors = [
  ["Motifs", "Recognisable accompaniment and melody fragments the owner can name."],
  ["Bass and harmony motion", "The harmonic movement and low-end direction that carry the song."],
  ["Groove and section energy", "How drums, feel and arrangement energy change between sections."],
  ["Lyrics, phrase and structure", "Canonical words, phrase boundaries and the song's shape."],
] as const;

const natureLabels = [
  ["D", "Deterministic", "Fixed code and rules edit audio, timing, manifests or edit maps. No learned weights are consulted or changed."],
  ["I", "Frozen-model inference", "Existing pretrained models are used for analysis or generation. The model is used, not trained."],
  ["T", "Model training", "An optimisation job changes learned weights. Every trained output stays a research challenger until real-song evidence earns promotion."],
  ["H", "Human musical review", "The musician listens, chooses, rejects and names what must stay. This is the musical authority."],
] as const;

export default function RemixResearch() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Remix research navigation">
          <a href="#status">Status</a>
          <a href="#remix-means">What counts as a remix</a>
          <a href="#labels">How the work is labelled</a>
          <a href="#boundaries">Boundaries</a>
        </nav>
        <ExternalLink className="header-cta" href={links.repo}>
          View the code ↗
        </ExternalLink>
      </header>

      <article className="agent-page vocal-research-page">
        <header>
          <div className="eyebrow">PRIVATE RESEARCH PLAN · NOTHING IMPLEMENTED YET</div>
          <h1>Change one thing. Keep the song.</h1>
          <p className="lede">
            Sunofriend is planning a second in-development feature:
            identity-preserving remixing. A bounded remix makes one intentional
            change—one instrument, role or region—while keeping the motifs,
            harmony, groove and structure the owner recognises from the source.
            No remix model is installed, trained or authorised yet.
          </p>
        </header>

        <section id="status" className="status-panel">
          <span className="card-number">WHAT IS TRUE TODAY</span>
          <h2>A canonical plan exists. The feature does not.</h2>
          <p>
            The public programme plan defines how remixing and audio-native
            vocal comping will be built together around a shared, time-aligned
            Musical State. That plan authorises no model installation, training,
            cloud upload or production feature by itself.
          </p>
          <p>
            There is no remix command, no trained model and no generation yet.
            The first remix controls are planned as deterministic assembly or
            retrieval with frozen pretrained models (D+I+H)—no training
            required. Learned conditioning (T+I+H) would begin only after
            repeated bounded remix evidence beats those controls on real songs.
          </p>
          <p>
            <ExternalLink className="text-link" href={links.semanticStatePlan}>
              Read the canonical Semantic Musical State programme plan ↗
            </ExternalLink>
          </p>
        </section>

        <section id="remix-means">
          <h2>What counts as a remix here.</h2>
          <p className="lede">
            Not unconstrained full-song regeneration. The owner names what must
            stay; the operation changes only what was permitted.
          </p>
          <div className="recording-route-grid">
            {identityAnchors.map(([name, explanation]) => (
              <article className="agent-card" key={name}>
                <span className="card-number">IDENTITY ANCHOR</span>
                <h3>{name}</h3>
                <p>{explanation}</p>
              </article>
            ))}
          </div>
          <ul className="check-list">
            <li><strong>One permitted change.</strong> A remix benchmark names the identity anchor and the single thing allowed to change—an instrument, a role, a region—before anything is rendered.</li>
            <li><strong>Bounded first.</strong> The first planned operations cover 8–16 bars, not a whole song.</li>
            <li><strong>Deterministic control first.</strong> Every learned or generated attempt is compared with a deterministic control, and fails if every owner-recognised anchor is lost.</li>
            <li><strong>Editable handoff.</strong> Reviewed results stay editable—MIDI/Clip assembly or region-level edits—and keep an exact source map.</li>
            <li><strong>Fixture-specific identity.</strong> Which elements carry identity is decided per track by listening; it must not become a universal rule.</li>
          </ul>
        </section>

        <section id="labels">
          <h2>How the work is labelled.</h2>
          <p className="lede">
            Every task and experiment declares what kind of work it is, so a
            trained model can never quietly stand in for human judgement.
          </p>
          <div className="workflow-grid">
            {natureLabels.map(([code, name, explanation]) => (
              <article className="workflow-step" key={code}>
                <span>{code}</span>
                <h3>{name}</h3>
                <p>{explanation}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="boundaries">
          <h2>What the design must protect.</h2>
          <ul className="check-list">
            <li><strong>Your audio stays local.</strong> The public site has no upload or hosted remix endpoint.</li>
            <li><strong>Listening outranks similarity scores.</strong> Embedding similarity and MIDI/F0 self-agreement do not establish the feature.</li>
            <li><strong>Training is gated.</strong> Local experiments may begin early, but every checkpoint is a challenger; larger or paid cloud training needs separate authorisation and never uploads private audio.</li>
            <li><strong>Generated audio is a labelled source class.</strong> It carries consent, training provenance and visible edit-map labelling; a human/AI duet is valid only when chosen by the user and is never described as fully human.</li>
            <li><strong>No acceptable result is a valid result.</strong> If neither the deterministic control nor any challenger keeps the named anchors, the failure is retained and the next cycle is chosen.</li>
          </ul>
        </section>

        <section className="status-panel">
          <span className="card-number">NEXT RESEARCH INCREMENT</span>
          <h2>One bounded remix on one authorised track.</h2>
          <p>
            The planned first cycle names a musical identity anchor and the one
            permitted change, renders a deterministic control, adds a frozen-model
            challenger only where it helps, and plays both against the track in a
            real music session. The accepted result—or the exact reason neither
            is useful—becomes the evidence for the next cycle.
          </p>
          <p>
            Development alternates between vocal comping and remixing on real
            songs, so both features are measured by playable artifacts, not
            metrics alone.
          </p>
        </section>

        <Link className="text-link back-link" href="/">
          ← Back to Sunofriend
        </Link>
      </article>
    </main>
  );
}
