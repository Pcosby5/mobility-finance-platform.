import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button, Dialog, Field, FormError, Input, Select } from "@/components/ui";
import { api, apiErrorMessage } from "@/lib/api";
import type { Currency, CustomerProfile, EmploymentStatus } from "@/types/api";

const EMPLOYMENT_OPTIONS: EmploymentStatus[] = [
  "EMPLOYED",
  "SELF_EMPLOYED",
  "UNEMPLOYED",
  "STUDENT",
];

const CURRENCY_OPTIONS: Currency[] = ["GHS", "NGN", "USD"];

type ProfileForm = {
  full_name: string;
  phone: string;
  employment_status: EmploymentStatus;
  employment_duration_months: string;
  currency: Currency;
  monthly_income: string;
  existing_debt: string;
  monthly_debt_repayment: string;
};

const EMPTY_FORM: ProfileForm = {
  full_name: "",
  phone: "",
  employment_status: "EMPLOYED",
  employment_duration_months: "",
  currency: "GHS",
  monthly_income: "",
  existing_debt: "0",
  monthly_debt_repayment: "0",
};

function toForm(profile: CustomerProfile): ProfileForm {
  return {
    full_name: profile.full_name,
    phone: profile.phone,
    employment_status: profile.employment_status,
    employment_duration_months:
      profile.employment_duration_months === null ? "" : String(profile.employment_duration_months),
    currency: profile.currency,
    monthly_income: profile.monthly_income,
    existing_debt: profile.existing_debt,
    monthly_debt_repayment: profile.monthly_debt_repayment,
  };
}

/**
 * Create (no `profile`) or edit (`profile`) a customer profile in a persistent
 * dialog. The dialog cannot be dismissed by outside clicks, so partially
 * entered financial data is never lost.
 */
export function ProfileDialog({
  open,
  onClose,
  profile,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  /** Existing profile to edit; omit to create. */
  profile?: CustomerProfile | null;
  /** Called after a successful save with the saved profile. */
  onSaved?: (saved: CustomerProfile) => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = profile != null;

  const [form, setForm] = useState<ProfileForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setForm(profile ? toForm(profile) : EMPTY_FORM);
      setError(null);
    }
  }, [open, profile]);

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      isEdit
        ? api.patch<CustomerProfile>(`/customers/${profile.id}/`, payload).then((r) => r.data)
        : api.post<CustomerProfile>("/customers/", payload).then((r) => r.data),
  });

  function update<K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    mutation.mutate(
      {
        full_name: form.full_name.trim(),
        phone: form.phone.trim(),
        employment_status: form.employment_status,
        employment_duration_months:
          form.employment_duration_months === "" ? null : Number(form.employment_duration_months),
        currency: form.currency,
        monthly_income: form.monthly_income,
        existing_debt: form.existing_debt || "0",
        monthly_debt_repayment: form.monthly_debt_repayment || "0",
      },
      {
        onSuccess: (saved) => {
          queryClient.invalidateQueries({ queryKey: ["customers"] });
          onSaved?.(saved);
          onClose();
        },
        onError: (err) => setError(apiErrorMessage(err)),
      },
    );
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="lg"
      title={isEdit ? "Edit customer profile" : "Create your financial profile"}
      description="Self-reported inputs for demo credit screening."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name">
            <Input
              value={form.full_name}
              onChange={(e) => update("full_name", e.target.value)}
              required
            />
          </Field>
          <Field label="Phone" hint="e.g. +233201234567">
            <Input
              value={form.phone}
              onChange={(e) => update("phone", e.target.value)}
              placeholder="+233…"
              required
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Employment status">
            <Select
              value={form.employment_status}
              onChange={(e) => update("employment_status", e.target.value as EmploymentStatus)}
            >
              {EMPLOYMENT_OPTIONS.map((status) => (
                <option key={status} value={status}>
                  {status.replace("_", " ")}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Employment duration (months)">
            <Input
              type="number"
              min={0}
              value={form.employment_duration_months}
              onChange={(e) => update("employment_duration_months", e.target.value)}
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Currency">
            <Select
              value={form.currency}
              onChange={(e) => update("currency", e.target.value as Currency)}
            >
              {CURRENCY_OPTIONS.map((currency) => (
                <option key={currency} value={currency}>
                  {currency}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Monthly income">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.monthly_income}
              onChange={(e) => update("monthly_income", e.target.value)}
              required
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Existing debt">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.existing_debt}
              onChange={(e) => update("existing_debt", e.target.value)}
            />
          </Field>
          <Field label="Monthly debt repayment">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.monthly_debt_repayment}
              onChange={(e) => update("monthly_debt_repayment", e.target.value)}
            />
          </Field>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Button type="submit" loading={mutation.isPending} className="flex-1">
            {isEdit ? "Save changes" : "Create profile"}
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
