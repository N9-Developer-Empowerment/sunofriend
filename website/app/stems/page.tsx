import type { Metadata } from "next";
import Link from "next/link";
import {
  links,
  stemBoundary,
  stemProviders,
} from "../content";

export const metadata: Metadata = {
  title: "What music stems are and where to get them",
  description:
    "A plain-language Sunofriend guide to music stems, authorised sources, local and cloud separation, privacy, folder import and the current WAV project boundary.",
  alternates: {
    canonical: "/stems/",
  },
};

export default function Stems() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Stems guide navigation">
          <a href="#meaning">Meaning</a>
          <a href="#routes">Where to get them</a>
          <a href="#providers">Provider guide</a>
          <a href="#check">Before you process</a>
        </nav>
        <Link className="header-cta" href="/demo/">
          Try the demo
        </Link>
      </header>

      <article className="agent-page guide-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            BEGINNER STEM GUIDE
          </div>
          <h1>What are stems?</h1>
          <p className="lede">
            A finished song is normally one stereo file. A stem is a separate,
            synchronized audio file containing a grouped part of that song,
            such as drums, bass, vocals or keys.
          </p>
          <p className="lede">
            A stem is <strong>not necessarily one instrument</strong>. A drums
            stem can contain kick, snare, hats, toms, cymbals and percussion.
            A keys stem can combine piano, organ, pads and synthesizers.
          </p>
          <div className="hero-actions">
            <Link className="button button-hot" href="/#codex">
              Start with the skill
            </Link>
            <Link className="button button-ghost" href="/glossary/">
              Open the glossary
            </Link>
          </div>
        </header>

        <section className="status-panel" aria-labelledby="today-title">
          <span className="card-number">WHAT WORKS TODAY</span>
          <h2 id="today-title">
            Bring separate audio parts. Prepare supported formats locally.
          </h2>
          <p>
            The complete MIDI, listening-WAV, Simple and Studio workflows still
            accept {stemBoundary.songProjectInputToday}. The local folder
            importer can prepare {stemBoundary.sourceFolderImportToday} as one
            project containing {stemBoundary.sourceFolderImportOutput}.
          </p>
          <p>
            Sunofriend does not yet separate one finished song into stems, and
            the public website does not receive audio. Folder preparation does
            not shift, pad, stretch, normalize or align parts, and it does not
            prove the musical downbeat.
          </p>
          <div className="prompt-stack">
            <div className="prompt-box">
              <div className="prompt-top">
                <span>CHECK THE LOCAL IMPORT TOOLCHAIN</span>
              </div>
              <textarea
                aria-label="Source doctor command"
                readOnly
                value={stemBoundary.sourceDoctorCommand}
                rows={2}
              />
            </div>
            <div className="prompt-box">
              <div className="prompt-top">
                <span>PLAN A FOLDER WITHOUT WRITING</span>
              </div>
              <textarea
                aria-label="Read-only source folder import plan command"
                readOnly
                value={stemBoundary.sourceFolderImportCommand}
                rows={3}
              />
            </div>
          </div>
          <p className="guide-note">
            Remove <code>--plan</code> only after checking the read-only plan.
            Execution replans the current files rather than replaying a stored
            plan, so plan again after any input, role-map or option change.
            Missing recorded-origin evidence requires the explicit{" "}
            <code>--accept-unconfirmed-origin</code> acknowledgement; that is
            not proof that the parts are aligned.
          </p>
          <p className="guide-note">
            For one standalone asset, <code>{stemBoundary.sourceImportCommand}</code>{" "}
            remains available. It does not make a complete song project.
          </p>
        </section>

        <section id="meaning">
          <h2>Why the distinction matters</h2>
          <div className="agent-grid">
            <article className="agent-card">
              <span className="card-number">ORIGINAL EXPORT</span>
              <h3>Made in the music project</h3>
              <p>
                If you made the song in a DAW, synchronized track or stem
                exports are normally the cleanest input. Export every part from
                the same start point to the same ending.
              </p>
            </article>
            <article className="agent-card">
              <span className="card-number">AI ESTIMATE</span>
              <h3>Separated from a finished mix</h3>
              <p>
                An AI separator estimates overlapping parts. It cannot recreate
                lost studio tracks exactly, so bleed, muffling and watery
                artefacts are normal and can become false MIDI notes.
              </p>
            </article>
          </div>
          <p className="guide-note">
            A broad stem may later be refined, such as drums into kick, snare,
            hats, toms, cymbals and other percussion. That refinement is another
            estimate. Do not include both a parent drum stem and all of its
            child stems in one arrangement, or parts will be duplicated.
          </p>
        </section>

        <section id="routes">
          <h2>Three practical routes</h2>
          <div className="journey-grid">
            <article className="journey-card journey-primary">
              <span className="card-number">1 / YOUR OWN PROJECT</span>
              <h3>Export from your DAW</h3>
              <p>
                Export synchronized parts from GarageBand or another DAW.
                Keep the same start, end, sample rate and song timing.
              </p>
              <small>Usually the cleanest route when you made the music.</small>
            </article>
            <article className="journey-card">
              <span className="card-number">2 / AUTHORISED PARTS</span>
              <h3>Use supplied stems</h3>
              <p>
                An artist, collaborator, generator project or education library
                may provide stems or multitracks. Check the licence for that
                exact project and intended use.
              </p>
              <small>Permission to practise is not permission to republish.</small>
            </article>
            <article className="journey-card">
              <span className="card-number">3 / SEPARATE A MIX</span>
              <h3>Use an independent tool</h3>
              <p>
                A local application or cloud service can estimate stems from a
                finished song you are authorised to process. Listen to every
                result before asking Sunofriend to transcribe it.
              </p>
              <small>Prefer lossless audio when it is available.</small>
            </article>
          </div>
        </section>

        <section id="providers">
          <h2>Neutral provider starting points</h2>
          <p className="lede">
            Features, prices, export formats and terms change. These are
            ordinary official links, not a quality ranking. No provider has
            yet passed Sunofriend&apos;s downstream MIDI bake-off.
          </p>
          <aside className="affiliate-disclosure">
            <strong>No current affiliate links.</strong> Sunofriend currently
            receives no commission from these links. If that changes, the
            relationship will be labelled beside the link and an ordinary
            non-tracked route will remain available.
          </aside>
          <div className="provider-grid">
            {stemProviders.map((provider) => (
              <article className="agent-card provider-card" key={provider.name}>
                <div className="provider-heading">
                  <span className="card-number">{provider.location}</span>
                  <a
                    className="text-link"
                    href={provider.href}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`${provider.name} official site (opens in a new tab)`}
                  >
                    {provider.name} official site ↗
                  </a>
                </div>
                <h3>{provider.name}</h3>
                <p>{provider.usefulFor}</p>
                <small>{provider.boundary}</small>
              </article>
            ))}
          </div>
        </section>

        <section id="check">
          <h2>Check before you process</h2>
          <ol className="check-list">
            <li>
              <strong>Rights:</strong> Do you own the recording, have
              permission, hold a suitable licence or have another lawful basis?
            </li>
            <li>
              <strong>Privacy:</strong> Is the song unreleased, confidential or
              commercially sensitive?
            </li>
            <li>
              <strong>Location:</strong> Does the chosen tool process on your
              Mac or upload the audio?
            </li>
            <li>
              <strong>Provider terms:</strong> How long are uploads and derived
              files retained, and may they be used to improve a service?
            </li>
            <li>
              <strong>Outputs:</strong> May you publish the MIDI, remix,
              sample-based instrument or separated audio?
            </li>
          </ol>
          <p className="guide-note">
            Owning a stream, download or subscription does not automatically
            grant permission to upload, adapt or redistribute the recording.
            This is practical product guidance, not legal advice.
          </p>
        </section>

        <section>
          <h2>What to bring back</h2>
          <div className="agent-grid">
            <article className="agent-card">
              <span className="card-number">FOR SUNOFRIEND TODAY</span>
              <h3>A folder of synchronized separated parts</h3>
              <ul>
                <li>one song per folder;</li>
                <li>2–64 top-level files intended to share a recorded start;</li>
                <li>WAV, AIFF, FLAC, M4A, MP3 or Ogg;</li>
                <li>clear names such as bass.flac and kick.wav;</li>
                <li>the song key and BPM if you know them.</li>
              </ul>
              <p>
                Use <code>source-import-folder --plan</code>, review its roles
                and origin evidence, then explicitly execute into a fresh
                project. It preserves a broad <code>drums</code> part for later
                composite handling.
              </p>
              <p>
                Do not map an observed part to <code>pads</code>: production
                currently synthesizes pads from keys. A genuinely string-like
                sustained part may be <code>strings</code>; otherwise leave it
                unresolved instead of mislabelling it.
              </p>
            </article>
            <article className="agent-card">
              <span className="card-number">NO STEMS REQUIRED</span>
              <h3>Try the safe demo instead</h3>
              <p>
                The built-in demo creates synthetic source stems and runs the
                normal automatic MIDI, listening-WAV and ZIP path.
              </p>
              <div className="journey-links">
                <Link className="text-link" href="/demo/">
                  Open the demo guide →
                </Link>
                <Link className="text-link text-link-muted" href="/#codex">
                  Install the skill →
                </Link>
              </div>
            </article>
          </div>
        </section>

        <div className="journey-links back-link">
          <Link className="text-link" href="/">
            ← Back to Sunofriend
          </Link>
          <a
            className="text-link text-link-muted"
            href={links.stemGuide}
            target="_blank"
            rel="noreferrer"
          >
            Read the maintained repository guide ↗
          </a>
        </div>
      </article>
    </main>
  );
}
