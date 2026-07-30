import type { Metadata } from "next";
import Link from "next/link";
import { links } from "../content";

export const metadata: Metadata = {
  title: "Contact Sunofriend",
  description:
    "Contact Sunofriend for private help, use GitHub for reproducible reports, or report a security issue privately.",
  alternates: {
    canonical: "/contact/",
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

export default function Contact() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Contact navigation">
          <a href="#email">Email</a>
          <a href="#support">Support</a>
          <a href="#security">Security</a>
          <Link href="/privacy/">Privacy</Link>
        </nav>
        <Link className="header-cta" href="/">
          Back home
        </Link>
      </header>

      <article className="agent-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            CONTACT SUNOFRIEND
          </div>
          <h1>Start in the place that protects your question.</h1>
          <p className="lede">
            Email is best for private context. GitHub is best for a reproducible
            bug or compatibility report. Security concerns have their own
            private reporting route.
          </p>
        </header>

        <section aria-label="Contact routes">
          <div className="agent-grid">
            <div className="agent-card" id="email">
              <span className="card-number">PRIVATE OR GENERAL</span>
              <h2>Email Sunofriend</h2>
              <p>
                Write to <a href={links.email}>hello@sunofriend.com</a>. Please
                allow up to two working days for a reply.
              </p>
              <div className="journey-links">
                <a className="text-link" href={links.email}>
                  Email hello@sunofriend.com →
                </a>
              </div>
            </div>

            <div className="agent-card" id="support">
              <span className="card-number">REPRODUCIBLE SUPPORT</span>
              <h2>Use a GitHub report</h2>
              <p>
                Use the structured forms for a first-song journey or another
                DAW, separator, AI tool or MIDI setup. Public reports help
                other musicians find the same answer.
              </p>
              <div className="journey-links">
                <ExternalLink className="text-link" href={links.firstSong}>
                  First-song report ↗
                </ExternalLink>
                <ExternalLink className="text-link" href={links.compatibility}>
                  DAW / AI compatibility report ↗
                </ExternalLink>
              </div>
            </div>

            <div className="agent-card" id="security">
              <span className="card-number">PRIVATE SECURITY REPORT</span>
              <h2>Do not open a public issue</h2>
              <p>
                Use GitHub&apos;s private vulnerability report so technical
                details can be discussed before disclosure.
              </p>
              <div className="journey-links">
                <ExternalLink className="text-link" href={links.securityReport}>
                  Report a vulnerability privately ↗
                </ExternalLink>
              </div>
            </div>

            <div className="agent-card">
              <span className="card-number">KEEP AUDIO LOCAL</span>
              <h2>Do not send stems or private music</h2>
              <p>
                Sunofriend is local-first. Do not email or attach stems, vocals,
                unreleased music, MIDI, project files or private review notes.
                Describe the problem and share only a minimal, authorised
                technical excerpt when it is genuinely needed.
              </p>
              <div className="journey-links">
                <Link className="text-link" href="/privacy/">
                  Read the privacy notice →
                </Link>
              </div>
            </div>
          </div>
        </section>
      </article>
    </main>
  );
}
