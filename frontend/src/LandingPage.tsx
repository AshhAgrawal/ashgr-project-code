type LandingPageProps = {
  authenticationEnabled: boolean;
  onSignIn: () => void;
  onSignUp: () => void;
};

const capabilities = [
  {
    number: "01",
    title: "Sell and serve",
    description:
      "Ring up purchases, process returns, and apply promotions through simple natural-language requests.",
  },
  {
    number: "02",
    title: "Stay in stock",
    description:
      "Check live inventory, receive purchase orders, and reorder low-stock products from the best supplier.",
  },
  {
    number: "03",
    title: "Know the story",
    description:
      "Surface revenue, margins, and stockout risk without digging through spreadsheets or disconnected tools.",
  },
];

export default function LandingPage({
  authenticationEnabled,
  onSignIn,
  onSignUp,
}: LandingPageProps) {
  return (
    <main className="landing-page">
      <nav className="landing-nav" aria-label="Main navigation">
        <a className="landing-brand" href="#top" aria-label="ashgr home">
          <img src="/assets/ashgr-wordmark.webp" alt="ashgr" />
          <span>Retail workspace</span>
        </a>
        <button className="nav-login" type="button" onClick={onSignIn}>
          {authenticationEnabled ? "Sign in" : "Open workspace"}{" "}
          <span aria-hidden="true">↗</span>
        </button>
      </nav>

      <section className="landing-hero" id="top">
        <div className="landing-hero-copy">
          <span className="landing-eyebrow">Retail operations, reimagined</span>
          <h1>
            Your store’s
            <br />
            <em>smartest teammate.</em>
          </h1>
          <p>
            One AI-powered workspace for the people who keep retail moving.
            Turn everyday requests into completed sales, returns, inventory
            updates, reorders, and reports—without switching systems.
          </p>
          <div className="landing-actions">
            <button type="button" onClick={onSignUp}>
              {authenticationEnabled
                ? "Create your workspace"
                : "Open retail workspace"}{" "}
              <span aria-hidden="true">→</span>
            </button>
            <a href="#how-it-works">See how it works</a>
          </div>
          <div className="landing-proof">
            <span>✦ Built for internal retail teams</span>
            <span>✦ Natural-language operations</span>
          </div>
        </div>

        <div className="workspace-preview" aria-label="Retail workspace preview">
          <div className="preview-glow preview-glow-one" />
          <div className="preview-glow preview-glow-two" />
          <div className="preview-window">
            <div className="preview-topbar">
              <div>
                <span className="preview-avatar">a</span>
                <p>
                  <strong>ashgr Assistant</strong>
                  <small>Online · Ready to help</small>
                </p>
              </div>
              <i />
            </div>
            <div className="preview-body">
              <div className="preview-message assistant">
                What would you like to get done today?
              </div>
              <div className="preview-prompt">
                Ring up two Classic Tees and one Canvas Tote for a walk-in.
              </div>
              <div className="preview-result">
                <span>✓</span>
                <div>
                  <strong>Sale complete</strong>
                  <small>Inventory updated · Receipt ready</small>
                </div>
                <b>$68.00</b>
              </div>
              <div className="preview-shortcuts">
                <span>Check inventory</span>
                <span>Reorder stock</span>
                <span>Run report</span>
              </div>
            </div>
          </div>
          <div className="floating-product floating-tee">
            <img src="/assets/ashgr-tee-blue.webp" alt="" />
            <span>Live inventory</span>
          </div>
          <div className="floating-metric">
            <span>Today</span>
            <strong>13</strong>
            <small>variants tracked</small>
          </div>
        </div>
      </section>

      <section className="landing-capabilities" id="how-it-works">
        <div className="capabilities-heading">
          <div>
            <span>One workspace, every shift</span>
            <h2>From request to retail action.</h2>
          </div>
          <p>
            Give store associates, inventory teams, and managers a faster way
            to complete the work behind every customer experience.
          </p>
        </div>
        <div className="capability-grid">
          {capabilities.map((capability) => (
            <article key={capability.number}>
              <span>{capability.number}</span>
              <h3>{capability.title}</h3>
              <p>{capability.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-workflow">
        <div className="workflow-copy">
          <span className="landing-eyebrow">Designed for your team</span>
          <h2>Less system-hopping. More work completed.</h2>
          <p>
            Workers simply describe what needs to happen. The assistant selects
            the right retail tool, applies your business rules, and returns a
            clear result your team can act on immediately.
          </p>
        </div>
        <ol>
          <li>
            <span>1</span>
            <div>
              <strong>Ask naturally</strong>
              <p>Type the same request you would give a teammate.</p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>The agent takes action</strong>
              <p>Approved retail tools handle the operation and calculations.</p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <strong>Get a clear result</strong>
              <p>Receive a concise receipt, confirmation, or business report.</p>
            </div>
          </li>
        </ol>
      </section>

      <section className="landing-cta">
        <span>Ready for the next shift?</span>
        <h2>Put your retail story to work.</h2>
        <button type="button" onClick={onSignUp}>
          {authenticationEnabled
            ? "Sign in to the workspace"
            : "Open the workspace"}{" "}
          <span aria-hidden="true">→</span>
        </button>
      </section>

      <footer className="landing-footer">
        <img src="/assets/ashgr-wordmark.webp" alt="ashgr" />
        <p>Premium retail, powered by smarter operations.</p>
      </footer>
    </main>
  );
}
