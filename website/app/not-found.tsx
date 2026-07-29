import Link from "next/link";

export default function NotFound() {
  return (
    <main className="not-found-page">
      <div className="noise" aria-hidden="true" />
      <section>
        <span className="card-number">SUNOFRIEND / 404</span>
        <h1>This page is silent.</h1>
        <p>
          The address does not match a Sunofriend page. Return home, learn what
          stems are, or try the copyright-safe demo.
        </p>
        <div className="hero-actions">
          <Link className="button button-hot" href="/">
            Return home
          </Link>
          <Link className="button button-ghost" href="/stems/">
            Learn about stems
          </Link>
          <Link className="button button-ghost" href="/demo/">
            Try the demo
          </Link>
        </div>
      </section>
    </main>
  );
}
