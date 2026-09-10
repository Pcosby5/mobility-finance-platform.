import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { Button, Card, Field, FormError, Input } from "@/components/ui";
import { apiErrorMessage } from "@/lib/api";

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    username: "",
    email: "",
    first_name: "",
    last_name: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
        ...(form.first_name.trim() ? { first_name: form.first_name.trim() } : {}),
        ...(form.last_name.trim() ? { last_name: form.last_name.trim() } : {}),
      });
      // Registration does not start a session: send the user to login.
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-6 text-center text-2xl font-bold tracking-tight text-indigo-600">
          Mobility Finance
        </h1>
        <Card title="Create a customer account">
          <form onSubmit={handleSubmit} className="space-y-4">
            <FormError message={error} />
            <Field label="Username">
              <Input
                value={form.username}
                onChange={(e) => update("username", e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </Field>
            <Field label="Email">
              <Input
                type="email"
                value={form.email}
                onChange={(e) => update("email", e.target.value)}
                autoComplete="email"
                required
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="First name">
                <Input
                  value={form.first_name}
                  onChange={(e) => update("first_name", e.target.value)}
                  autoComplete="given-name"
                />
              </Field>
              <Field label="Last name">
                <Input
                  value={form.last_name}
                  onChange={(e) => update("last_name", e.target.value)}
                  autoComplete="family-name"
                />
              </Field>
            </div>
            <Field
              label="Password"
              hint="At least 8 characters; cannot be too similar to your username."
            >
              <Input
                type="password"
                value={form.password}
                onChange={(e) => update("password", e.target.value)}
                autoComplete="new-password"
                required
              />
            </Field>
            <Button type="submit" loading={submitting} className="w-full">
              Register
            </Button>
            <p className="text-center text-sm text-slate-500">
              Already registered?{" "}
              <Link to="/login" className="font-semibold text-indigo-600 hover:underline">
                Sign in
              </Link>
            </p>
          </form>
        </Card>
      </div>
    </div>
  );
}
