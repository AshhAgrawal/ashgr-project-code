import { FormEvent, useState } from "react";

export type AuthUser = {
  id: string;
  name: string;
  email: string;
  role: "admin" | "staff";
  account_type: "member" | "guest";
};

type AuthMode = "login" | "signup";

type AuthPageProps = {
  mode: AuthMode;
  apiUrl: string;
  onAuthenticated: (user: AuthUser) => void;
  onNavigate: (mode: AuthMode | "home") => void;
};

export default function AuthPage({
  mode,
  apiUrl,
  onAuthenticated,
  onNavigate,
}: AuthPageProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isSignup = mode === "signup";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (isSignup && password !== confirmation) {
      setError("Passwords do not match.");
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      const response = await fetch(`${apiUrl}/api/auth/${mode}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          isSignup ? { name, email, password } : { email, password },
        ),
      });
      const body = (await response.json()) as {
        user?: AuthUser;
        detail?: string | Array<{ msg?: string }>;
      };
      if (!response.ok || !body.user) {
        const detail = Array.isArray(body.detail)
          ? body.detail[0]?.msg
          : body.detail;
        throw new Error(detail || "Authentication failed.");
      }
      onAuthenticated(body.user);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Authentication failed.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function continueAsGuest() {
    setError(null);
    setIsSubmitting(true);
    try {
      const response = await fetch(`${apiUrl}/api/auth/guest`, {
        method: "POST",
        credentials: "include",
      });
      const body = (await response.json()) as {
        user?: AuthUser;
        detail?: string;
      };
      if (!response.ok || !body.user) {
        throw new Error(body.detail || "Guest access is unavailable.");
      }
      onAuthenticated(body.user);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Guest access is unavailable.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="About ashgr retail workspace">
        <button
          className="auth-brand"
          type="button"
          onClick={() => onNavigate("home")}
          aria-label="Back to ashgr home"
        >
          <img src="/assets/ashgr-wordmark.webp" alt="ashgr" />
          <span>Retail workspace</span>
        </button>
        <div className="auth-story-copy">
          <span className="landing-eyebrow">Your store, in sync</span>
          <h1>
            Operations move
            <br />
            <em>at your pace.</em>
          </h1>
          <p>
            Sign in to manage live inventory, complete retail operations, and
            ask the ashgr Assistant what needs attention next.
          </p>
          <div className="auth-proof-grid">
            <article>
              <strong>Live</strong>
              <span>MongoDB inventory</span>
            </article>
            <article>
              <strong>24/7</strong>
              <span>AI operations support</span>
            </article>
          </div>
        </div>
        <div className="auth-shape auth-shape-one" />
        <div className="auth-shape auth-shape-two" />
      </section>

      <section className="auth-form-panel">
        <div className="auth-form-wrap">
          <button
            className="auth-back"
            type="button"
            onClick={() => onNavigate("home")}
          >
            ← Back to home
          </button>
          <header>
            <span>{isSignup ? "Start your workspace" : "Welcome back"}</span>
            <h2>{isSignup ? "Create your account" : "Sign in to ashgr"}</h2>
            <p>
              {isSignup
                ? "Set up secure access to your retail workspace."
                : "Use the account connected to your retail team."}
            </p>
          </header>

          <form className="auth-form" onSubmit={submit}>
            {isSignup && (
              <label>
                <span>Full name</span>
                <input
                  type="text"
                  name="name"
                  autoComplete="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Alex Morgan"
                  minLength={2}
                  maxLength={80}
                  required
                />
              </label>
            )}
            <label>
              <span>Email address</span>
              <input
                type="email"
                name="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                required
              />
            </label>
            <label>
              <span>Password</span>
              <input
                type="password"
                name="password"
                autoComplete={isSignup ? "new-password" : "current-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 10 characters"
                minLength={isSignup ? 10 : 1}
                maxLength={256}
                required
              />
            </label>
            {isSignup && (
              <label>
                <span>Confirm password</span>
                <input
                  type="password"
                  name="password-confirmation"
                  autoComplete="new-password"
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  placeholder="Enter your password again"
                  minLength={10}
                  maxLength={256}
                  required
                />
              </label>
            )}

            {error && (
              <div className="auth-error" role="alert">
                {error}
              </div>
            )}

            <button className="auth-submit" type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? "Please wait…"
                : isSignup
                  ? "Create account"
                  : "Sign in"}
              {!isSubmitting && <span aria-hidden="true">→</span>}
            </button>
          </form>

          <div className="auth-divider">
            <span>or</span>
          </div>
          <button
            className="guest-submit"
            type="button"
            onClick={() => void continueAsGuest()}
            disabled={isSubmitting}
          >
            <span className="guest-icon" aria-hidden="true">G</span>
            <span>
              <strong>Continue as guest</strong>
              <small>No account details required</small>
            </span>
            <b aria-hidden="true">→</b>
          </button>

          <p className="auth-switch">
            {isSignup ? "Already have an account?" : "New to ashgr?"}{" "}
            <button
              type="button"
              onClick={() => onNavigate(isSignup ? "login" : "signup")}
            >
              {isSignup ? "Sign in" : "Create an account"}
            </button>
          </p>
          <p className="auth-security">
            <span aria-hidden="true">⌁</span> Passwords are salted and hashed
            before storage.
          </p>
        </div>
      </section>
    </main>
  );
}
