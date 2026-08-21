import type { Metadata } from "next";
import Link from "next/link";
import { links, separationResearch } from "../../content";

export const metadata: Metadata = {
  title: "Experimental local stem separation",
  description:
    "Public local two-stem and explicit SCNet core-four previews, with private six-role research and model-free recovery evidence kept clearly separate.",
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
          <a href="#working">Current lanes</a>
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
            PUBLIC EXPERIMENTAL PREVIEW · AUDIO STAYS LOCAL
          </div>
          <h1>Try two stems—or opt in to four.</h1>
          <p className="lede">
            The public default estimates broad vocals and complementary
            instrumental. An explicitly installed SCNet profile adds a public
            opt-in vocals, drums, bass and grouped-other preview. Six-role
            synth-and-guitar work remains private, unregistered research.
          </p>
        </header>

        <section id="working">
          <h2>Four lanes, two public</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">PUBLIC DEFAULT</span>
              <h3>Broad vocals and instrumental</h3>
              <p>
                One authorised finished mix becomes broad vocals, broad
                instrumental and a diagnostic reconstruction.
              </p>
              <p>
                The instrumental is the complement of the vocal estimate. It
                does not claim separate drums, bass, synth or guitar.
              </p>
            </div>

            <div className="agent-card">
              <span className="card-number">PUBLIC EXPLICIT OPT-IN</span>
              <h3>SCNet core four</h3>
              <p>
                Profile <code>scnet-large-musdb-release-v1</code> in scope{" "}
                <code>core-four-stems-v1</code> estimates vocals, drums, bass
                and grouped other. The pinned 168,848,417-byte checkpoint,
                offline synthetic check, three authorised full-song canaries
                and repeat resource runs passed their objective gates. Complete
                listens reported no catastrophic defect.
              </p>
              <p>
                This is a public opt-in preview, not recovered studio
                multitracks. A 36 GB M3 Max is the first verified machine class;
                other Apple-silicon classes remain accessible but unverified.
              </p>
            </div>

            <div className="agent-card">
              <span className="card-number">PRIVATE UNREGISTERED RESEARCH</span>
              <h3>Six roles with synth and guitar</h3>
              <p>
                Private Studio experiments combine SCNet core four with
                Mega-53 synth and BS-RoFormer-SW guitar specialists, constrained
                inside grouped other. The review roles are vocals, drums, bass,
                synth, guitar and residual other.
              </p>
              <p>
                These specialists are unregistered. There is no public
                six-role command, automatic source choice or activation. Exact
                reconstruction records accounting only, not separation quality.
              </p>
            </div>

            <div className="agent-card">
              <span className="card-number">PRIVATE MODEL-FREE RECOVERED REVIEW</span>
              <h3>
                <code>
                  private_review_package_recovered_model_free_resource_gate_incomplete
                </code>
              </h3>
              <p>
                The original plan was consumed once. Its replacement run
                historically completed 3 model loads and 9 completed inference
                attempts, but did not persist the guitar worker receipt. A
                separately approved network-denied recovery then reused 21
                retained private audio payloads and wrote a private review
                package without loading or running a separator: 0 checkpoint
                loads, 0 model constructions, 0 model loads, 0 inference
                attempts, 0 canonicalisations, 0 model-worker subprocesses and
                0 network attempts. One parent sandbox re-exec provided
                security supervision.
              </p>
              <p>
                All 24 new PCM24 review artifacts reconstruct within 0 LSB, but the
                guitar worker result receipt and guard counters were not
                persisted and guitar peak-memory evidence is absent. Therefore
                the guitar resource gate and full resource gate are incomplete,
                <code> within_known_ceilings</code> is unknown, and full
                objective qualification is false.
              </p>
              <p>
                Evidence binds plan{" "}
                <code>
                  869ac229d5c95c9c3d5eb2c9eb38da368056f6fe3c644de9830cc593313efb7d
                </code>
                , recovery request{" "}
                <code>
                  686a47f09b2f2e95a670e621aa75582e27bb14cebc64035f5c56af3c77f3e60c
                </code>{" "}
                and recovery report{" "}
                <code>
                  42500c2e9542aee5fc0e238697733923586ad1e37c54b1359a496cf832f330a0
                </code>
                . Its bound review is complete with status{" "}
                <code>human_listening_complete_no_selection</code>, document{" "}
                <code>
                  093347845c41bb0c456a10564701961c627fea5737486a901627b0c4f5208a86
                </code>
                : all 3/3
                songs were useful and non-catastrophic; core roles were useful
                in 3/3, and synth and guitar were each useful in 2/2
                confirmed-present cases. No scored role reported bleed,
                artefacts or timing/join problems. Both specialists reported
                some missing content in 2/2 cases. There were no cannot-tell or
                not-tested ratings.
              </p>
              <p>
                This is positive private musical evidence, not objective or
                resource qualification. The immutable private outcome status is{" "}
                <code>
                  private_full_song_six_role_listening_evidence_recorded_resource_gate_incomplete
                </code>
                , document{" "}
                <code>
                  fa5d1d24627dce4cb1e27175055f1e3d5a3a70683b98e2376d92ee125bc2163c
                </code>
                . The next technical gate is a newly bounded objective-only
                plan that records the repaired guitar worker receipt, guard
                counters and peak memory. Recovery, review and outcome recording
                performed no automatic retry, public activation, source selection,
                MIDI, hosting, redistribution, audio upload or model download.
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
            Start with the Sunofriend skill if you want guided setup. A
            model/runtime download is separate from the ordinary demo and needs
            explicit approval.
          </p>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">01 · INSPECT SETUP</span>
              <h3>Plan before downloading</h3>
              <p>
                Run <code>{separationResearch.setupPlanCommand}</code> for the
                default or{" "}
                <code>scripts/setup-separation-core-four-scnet-macos.sh --plan</code>{" "}
                for core four. Planning explains terms, size, network use and
                install location without changing the Mac.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">02 · VERIFY</span>
              <h3>Check the exact local profile</h3>
              <p>
                After explicit installation, run{" "}
                <code>{separationResearch.developerDoctorCommand}</code>. Doctor
                hashes the pinned files without loading the model or processing
                audio.
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
                Add <code>--execute --confirm-rights --open-review</code>. Judge
                usefulness, bleed, missing content, texture and joins before
                using any stem.
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
            One baseline configuration and one remediation cycle prevent an
            endless listening-feedback veto. Objective integrity, privacy and
            execution gates admit a preview; musical feedback records
            limitations and guides bounded challengers.
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
            Reports are reviewed after 30 days or 10 valid submissions,
            whichever comes first. Poor feedback cannot disable the last
            objectively functioning profile or silently select a model.
          </p>
        </section>

        <section id="limits">
          <h2>What remains experimental</h2>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">PUBLIC STATUS</span>
              <h3>{separationResearch.status}</h3>
              <p>
                Both routes remain separate local commands rather than a
                Simple/TUI default. The website receives no audio.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">NO PUBLIC SIX-ROLE CLAIM</span>
              <h3>Synth and guitar remain private research</h3>
              <p>
                The recovered six-role review does not register profiles,
                authorize public activation or establish full objective or
                resource qualification.
              </p>
            </div>
            <div className="agent-card">
              <span className="card-number">NOT GROUND TRUTH</span>
              <h3>Reconstruction is necessary, not sufficient</h3>
              <p>
                Exact additive accounting cannot prove clean isolation,
                musical usefulness or similarity to lost studio tracks.
              </p>
            </div>
          </div>
        </section>

        <section id="feedback">
          <h2>Help improve the public previews</h2>
          <p className="lede">{separationResearch.feedbackBoundary}</p>
          <div className="agent-grid">
            <div className="agent-card">
              <span className="card-number">MUSICIANS</span>
              <h3>Tell us whether the stems helped</h3>
              <p>
                Report overall and per-role usefulness, bleed, missing content,
                artefacts, timing and joins. “Cannot tell” and “Not tested” are
                valid.
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
                stems, review JSON, filenames or metadata.
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
