import type { Metadata } from "next";
import Link from "next/link";
import { links } from "../content";

export const metadata: Metadata = {
  title: "Privacy notice",
  description:
    "How Unsigned Media Ltd handles personal information sent through Sunofriend contact and support routes.",
  alternates: {
    canonical: "/privacy/",
  },
};

export default function Privacy() {
  return (
    <main>
      <div className="noise" aria-hidden="true" />
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Sunofriend home">
          <span className="wordmark-mark">S</span>
          <span>SUNOFRIEND</span>
        </Link>
        <nav aria-label="Privacy navigation">
          <a href="#information">Information</a>
          <a href="#use">Use</a>
          <a href="#retention">Retention</a>
          <a href="#rights">Rights</a>
        </nav>
        <Link className="header-cta" href="/contact/">
          Contact
        </Link>
      </header>

      <article className="agent-page">
        <header>
          <div className="eyebrow">
            <span className="live-dot" aria-hidden="true" />
            PRIVACY NOTICE · 30 JULY 2026
          </div>
          <h1>Private questions should stay proportionate.</h1>
          <p className="lede">
            Unsigned Media Ltd, company number 17046305, is responsible for
            personal information sent through Sunofriend&apos;s contact and
            support routes. Contact us at{" "}
            <a href={links.email}>hello@sunofriend.com</a>.
          </p>
        </header>

        <section id="information">
          <h2>Information we receive</h2>
          <div className="agent-card">
            <p>
              We receive the name, email address, message and technical details
              that you choose to send. Public GitHub reports also contain the
              account name and content that GitHub displays with the report.
            </p>
            <p>
              Do not send stems, vocals, unreleased music, MIDI, private project
              files, passwords, access tokens or information about another
              person that is not necessary for the question.
            </p>
          </div>
        </section>

        <section id="use">
          <h2>Why we use it</h2>
          <div className="agent-card">
            <p>
              We use contact information to answer enquiries, investigate
              support reports, maintain the security of Sunofriend and improve
              its documentation and software. We rely on our legitimate
              interests in operating and improving the project, steps requested
              by the person contacting us where relevant, and legal obligations
              when they apply.
            </p>
            <p>
              Incoming email is forwarded by Hover and handled in Google Gmail.
              Outgoing Sunofriend email is delivered through Amazon Web
              Services. Public support reports are handled by GitHub under
              those providers&apos; respective terms and privacy notices. We do
              not sell contact information.
            </p>
            <p>
              These global providers may process information outside the UK.
              Where a restricted transfer occurs, we rely on the provider&apos;s
              applicable transfer mechanism and safeguards described in its
              privacy and data-protection terms.
            </p>
          </div>
        </section>

        <section id="retention">
          <h2>Retention and protection</h2>
          <div className="agent-card">
            <p>
              We keep correspondence only while it is useful for the enquiry,
              security, project history or an applicable legal requirement. We
              review retained correspondence and delete or anonymise material
              that is no longer needed.
            </p>
            <p>
              The public website does not accept audio uploads and does not
              provide a hosted Sunofriend conversion service. Music processing,
              review notes and feedback remain on the user&apos;s local Mac.
            </p>
          </div>
        </section>

        <section id="rights">
          <h2>Your choices and rights</h2>
          <div className="agent-card">
            <p>
              You may ask about, correct or request deletion of personal
              information we hold, object to or restrict certain uses, or ask
              for a portable copy where the relevant right applies. Email{" "}
              <a href={links.email}>hello@sunofriend.com</a>. You may also
              complain to the UK Information Commissioner&apos;s Office.
            </p>
            <h3>Your right to object</h3>
            <p>
              You may object to our use of your personal information where we
              rely on legitimate interests. Tell us what you object to and why
              by emailing <a href={links.email}>hello@sunofriend.com</a>. We
              will stop that use unless we have a compelling legitimate reason
              to continue or need it for a legal claim.
            </p>
            <div className="journey-links">
              <a
                className="text-link"
                href="https://ico.org.uk/make-a-complaint/"
                target="_blank"
                rel="noreferrer"
              >
                Information Commissioner&apos;s Office ↗
              </a>
              <Link className="text-link" href="/contact/">
                Contact Sunofriend →
              </Link>
            </div>
          </div>
        </section>
      </article>
    </main>
  );
}
