import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { Button, Card, Field, FormError, Input } from "@/components/ui";
import { apiErrorMessage } from "@/lib/api";
import { RegisterDialog } from "@/pages/Register";
import { useTheme } from "@/theme/useTheme";

export function LoginPage() {
  const { login } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showRegister, setShowRegister] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";
      navigate(from, { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative grid min-h-svh overflow-hidden bg-[radial-gradient(circle_at_top_left,var(--page-glow)_0,var(--page-bg)_34rem)] px-4 py-8 lg:grid-cols-[1.1fr_0.9fr] lg:px-8">
      <button
        type="button"
        onClick={toggleTheme}
        className="absolute right-4 top-4 grid size-10 place-items-center rounded-full bg-[color:var(--nav-active)] text-[color:var(--text-strong)] shadow-sm ring-1 ring-[color:var(--line-soft)] transition hover:scale-[1.02] sm:right-8 sm:top-8"
        aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
        title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
      >
        {theme === "light" ? (
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            className="size-4"
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.8 6.8 0 0 0 9.8 9.8Z"
            />
          </svg>
        ) : (
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            className="size-4"
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.4-6.4L17 7M7 17l-1.4 1.4m12.8 0L17 17M7 7 5.6 5.6"
            />
            <circle cx="12" cy="12" r="4" />
          </svg>
        )}
      </button>
      <section className="hidden items-center justify-center lg:flex">
        <div className="max-w-xl">
          <div className="mb-8 inline-flex items-center gap-3 rounded-full bg-[color:var(--surface-bg)] px-4 py-2 text-sm font-semibold text-[color:var(--text-main)] shadow-sm ring-1 ring-[color:var(--surface-border)] backdrop-blur">
            <span className="size-2 rounded-full bg-emerald-500" />
            FinTech and fleet operations workspace
          </div>
          <h1 className="text-5xl font-semibold tracking-tight text-[color:var(--text-strong)] xl:text-6xl">
            Mobility finance, built like a serious operations product.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-[color:var(--text-muted)]">
            Credit decisions, vehicle assignment, loan schedules, payment verification and telemetry alerts in one clean backend demo.
          </p>
          <div className="mt-8 grid max-w-lg grid-cols-3 gap-3 xl:mt-10">
            {["Credit", "Loans", "IoT Fleet"].map((item) => (
              <div key={item} className="glass-panel rounded-3xl px-4 py-5">
                <p className="text-sm font-semibold text-[color:var(--text-strong)]">{item}</p>
                <p className="mt-1 text-xs leading-5 text-[color:var(--text-muted)]">Production-shaped flow</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="flex items-center justify-center">
        <div className="w-full max-w-md">
          <div className="mb-8 text-center lg:hidden">
            <div className="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-[color:var(--brand-block)] text-sm font-semibold text-[color:var(--brand-text)] shadow-lg shadow-slate-950/15">
              MF
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-strong)]">
              Mobility Finance
            </h1>
            <p className="mt-2 text-sm text-[color:var(--text-muted)]">Credit, fleet and payments workspace</p>
          </div>
          <Card title="Sign in">
            <form onSubmit={handleSubmit} className="space-y-4">
              <FormError message={error} />
              <Field label="Username">
                <Input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                />
              </Field>
              <Field label="Password">
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </Field>
              <Button type="submit" loading={submitting} className="w-full">
                Sign in
              </Button>
              <p className="text-center text-sm text-[color:var(--text-muted)]">
                No account?{" "}
                <button
                  type="button"
                  onClick={() => setShowRegister(true)}
                  className="font-semibold text-link hover:underline"
                >
                  Register
                </button>
              </p>
            </form>
          </Card>
          <p className="mt-4 text-center text-xs text-[color:var(--text-muted)]">
            Public registration creates customer accounts only. Staff roles stay operator-controlled.
          </p>
        </div>
      </div>
      <RegisterDialog open={showRegister} onClose={() => setShowRegister(false)} />
    </div>
  );
}
