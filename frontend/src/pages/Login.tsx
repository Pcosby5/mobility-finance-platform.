import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { Button, Card, Field, FormError, Input } from "@/components/ui";
import { apiErrorMessage } from "@/lib/api";
import { RegisterDialog } from "@/pages/Register";

export function LoginPage() {
  const { login } = useAuth();
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
    <div className="grid min-h-svh bg-[radial-gradient(circle_at_top_left,#e0e7ff_0,#f8fafc_34rem)] px-4 py-8 lg:grid-cols-[1.1fr_0.9fr] lg:px-8">
      <section className="hidden items-center justify-center lg:flex">
        <div className="max-w-xl">
          <div className="mb-8 inline-flex items-center gap-3 rounded-full bg-white/75 px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm ring-1 ring-white/80 backdrop-blur">
            <span className="size-2 rounded-full bg-emerald-500" />
            FinTech and fleet operations workspace
          </div>
          <h1 className="text-6xl font-semibold tracking-tight text-slate-950">
            Mobility finance, built like a serious operations product.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-slate-600">
            Credit decisions, vehicle assignment, loan schedules, payment verification and telemetry alerts in one clean backend demo.
          </p>
          <div className="mt-10 grid max-w-lg grid-cols-3 gap-3">
            {["Credit", "Loans", "IoT Fleet"].map((item) => (
              <div key={item} className="glass-panel rounded-3xl px-4 py-5">
                <p className="text-sm font-semibold text-slate-950">{item}</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">Production-shaped flow</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="flex items-center justify-center">
        <div className="w-full max-w-md">
          <div className="mb-8 text-center lg:hidden">
            <div className="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-slate-950 text-sm font-semibold text-white shadow-lg shadow-slate-950/15">
              MF
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-950">
              Mobility Finance
            </h1>
            <p className="mt-2 text-sm text-slate-500">Credit, fleet and payments workspace</p>
          </div>
          <Card title="Sign in" className="rounded-[2rem]">
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
            <p className="text-center text-sm text-slate-500">
              No account?{" "}
              <button
                type="button"
                onClick={() => setShowRegister(true)}
                className="font-semibold text-indigo-600 hover:underline"
              >
                Register
              </button>
            </p>
          </form>
        </Card>
        <p className="mt-4 text-center text-xs text-slate-500">
          Public registration creates customer accounts only. Staff roles stay operator-controlled.
        </p>
      </div>
      </div>
      <RegisterDialog open={showRegister} onClose={() => setShowRegister(false)} />
    </div>
  );
}
