import { useState, type FormEvent } from "react";

import { useAuth } from "@/auth/AuthContext";
import { Button, Dialog, Field, FormError, Input } from "@/components/ui";
import { apiErrorMessage } from "@/lib/api";

/** Registration dialog: creates a CUSTOMER account; does not start a session. */
export function RegisterDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { register } = useAuth();

  const [form, setForm] = useState({
    username: "",
    email: "",
    first_name: "",
    last_name: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState(false);

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function reset() {
    setForm({ username: "", email: "", first_name: "", last_name: "", password: "" });
    setError(null);
    setSubmitting(false);
    setCreated(false);
  }

  function handleClose() {
    onClose();
    // Reset after the dialog is gone so the closing frame keeps its content.
    window.setTimeout(reset, 200);
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
      setSubmitting(false);
      setCreated(true);
    } catch (err) {
      setSubmitting(false);
      setError(apiErrorMessage(err));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title={created ? "Account created" : "Create a customer account"}
      description={
        created
          ? undefined
          : "Registration creates a CUSTOMER sign-in. You will add your financial profile after signing in."
      }
    >
      {created ? (
        <div className="space-y-4">
          <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700 ring-1 ring-inset ring-emerald-200">
            Your account is ready. Sign in to continue.
          </p>
          <Button onClick={handleClose} className="w-full">
            Go to sign in
          </Button>
        </div>
      ) : (
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
          <div className="grid gap-3 sm:grid-cols-2">
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
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button type="submit" loading={submitting} className="flex-1">
              Register
            </Button>
            <Button type="button" variant="secondary" onClick={handleClose}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
