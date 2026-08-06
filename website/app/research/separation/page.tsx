import type { Metadata } from "next";
import Link from "next/link";
import { links, separationResearch } from "../../content";

export const metadata: Metadata = {
  title: "Experimental local stem separation — Sunofriend",
  description:
    "Try Sunofriend's public two-stem separator or explicit local SCNet core-four preview, and inspect the Studio-only grouped-other refinement contract.",
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
            PUBLIC EXPERIMENTAL PREVIEW · AUDIO STAYS LOCAL
          </div>
          <h1>Try two stems—or opt in to four.</h1>
          <p className="lede">
            Sunofriend defaults to broad vocals and complementary instrumental
            from one authorised finished song on an Apple-silicon Mac. The
            installed SCNet-large profile adds an explicit local vocals, drums,
            bass and grouped-other public opt-in preview.
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
              <span className="card-number">CORE-FOUR PUBLIC OPT-IN</span>
              <h3>Four roles, one immutable profile, no hidden tuning loop</h3>
              <p>
                The pinned Demucs MLX worker targets vocals, drums, bass and
                grouped other with network denial and exact PCM24 reconstruction
                accounting. Both permitted activation attempts failed before
                publication. The revised PyTorch CPU fallback passed install and
                doctor but rejected its native Fraction segment before inference,
                so its retries are also disabled. The separately pinned SCNet
                release profile now supplies the public opt-in execution path.
              </p>
              <p>
                Official SCNet-large is the installed public opt-in profile. Its
                four-role architecture and minimal
                Apple-arm64 runtime are pinned. An approved evidence-only
                download established the mutable Google Drive checkpoint&apos;s
                exact 168,848,417-byte identity and SHA-256 under accepted
                provisional terms evidence. Weights-only compatibility passed
                after one transparent official-wrapper remediation. A
                network-denied 60-second synthetic run then produced every role
                in 69.97 seconds at 6.58 GB peak RSS with zero-LSB
                reconstruction error. Very weak synthetic vocal output is a
                recorded limitation, not a reason to restart tuning. Three
                authorised full-song canaries passed, and complete listening
                checks reported no catastrophic defect. A 36 GB M3 Max is the
                first verified class; other Apple-silicon machines remain
                accessible but unverified.
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
              <span className="card-number">STUDIO RESEARCH CONTRACT</span>
              <h3>One guitar or keys target, with the residual kept</h3>
              <p>
                <code>other-refinement-v1</code> now binds one exact grouped-other
                parent to one requested guitar or keys target plus a transparent
                PCM24 residual. The parent and children cannot both enter MIDI.
              </p>
              <p>
                The first exact candidate is now pinned as{" "}
                <code>Apple-native htdemucs_6s MLX</code>, with guitar direct and
                keys honestly labelled as a piano proxy. It remains blocked and
                uninstalled. Its config repeats the known <code>39/5</code> segment
                issue, so one in-memory fraction normalization is the only allowed
                remediation. The setup plan is read-only and no public refinement
                command exists.
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
                Run <code>{separationResearch.setupPlanCommand}</code> for the
                default, or{" "}
                <code>scripts/setup-separation-core-four-scnet-macos.sh --plan</code>{" "}
                for core four. Each explains platform, model terms, size,
                network use and install location without changing the Mac.
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
            Development now has a hard stopping rule: one baseline configuration,
            one remediation cycle, then publish if objective gates pass or switch
            backend if they do not. Musical ratings are preserved for limitations
            and challengers, not used as an endless pre-release veto.
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
            Reports are reviewed after 30 days or 10 valid submissions, whichever
            comes first. Poor feedback cannot disable the last objectively
            functioning profile or silently select a model.
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
                Report overall and per-role usefulness, bleed, missing content,
                artefacts, timing, joins and whether downstream MIDI improved.
                “Cannot tell” and “Not tested” are valid.
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
                coding agent and exact command. Use Copy text-only feedback. Do
                not attach private audio, stems, review JSON, filenames or metadata.
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
