import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { canManage, useAuth } from "@/auth/AuthContext";
import {
  Badge,
  Button,
  Card,
  Dialog,
  EmptyState,
  Field,
  FormError,
  Input,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { api, apiErrorMessage, listAll } from "@/lib/api";
import { loanTone, money, relativeTime } from "@/lib/format";
import type { CreditAssessment, CustomerProfile, Loan, Vehicle } from "@/types/api";

/** An assessment is usable for origination when approved and younger than the policy age. */
const ASSESSMENT_AGE_DAYS = 30;

function isEligibleAssessment(assessment: CreditAssessment): boolean {
  if (assessment.decision !== "APPROVED") return false;
  const created = new Date(assessment.created_at).getTime();
  if (Number.isNaN(created)) return false;
  return Date.now() - created <= ASSESSMENT_AGE_DAYS * 24 * 60 * 60 * 1000;
}

type OriginationForm = {
  customer: string;
  vehicle: string;
  credit_assessment: string;
  principal_amount: string;
  annual_interest_rate: string;
  duration_months: string;
  first_repayment_date: string;
};

const EMPTY_FORM: OriginationForm = {
  customer: "",
  vehicle: "",
  credit_assessment: "",
  principal_amount: "",
  annual_interest_rate: "",
  duration_months: "",
  first_repayment_date: "",
};

function OriginationDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<OriginationForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
  });
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => listAll<Vehicle>("/vehicles/"),
  });
  // Assessments are fetched per selected customer via the customer-scoped endpoint.
  const assessments = useQuery({
    queryKey: ["customers", form.customer, "assessments"],
    queryFn: () =>
      listAll<CreditAssessment>(`/customers/${form.customer}/credit-assessments/`),
    enabled: form.customer !== "",
  });

  const selectedCustomer = (customers.data ?? []).find((c) => c.id === form.customer);
  // The backend enforces one open loan per vehicle at creation time; a
  // conflicting choice surfaces as a form error there.
  const eligibleVehicles = (vehicles.data ?? []).filter(
    (vehicle) => vehicle.customer === form.customer && vehicle.status === "ACTIVE",
  );
  const eligibleAssessments = (assessments.data ?? []).filter(isEligibleAssessment);

  const createLoan = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post<Loan>("/loans/", payload).then((r) => r.data),
    onSuccess: () => {
      setError(null);
      setForm(EMPTY_FORM);
      queryClient.invalidateQueries({ queryKey: ["loans"] });
      onClose();
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  function update<K extends keyof OriginationForm>(key: K, value: OriginationForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    createLoan.mutate({
      customer: form.customer,
      vehicle: form.vehicle,
      credit_assessment: form.credit_assessment,
      principal_amount: form.principal_amount,
      annual_interest_rate: form.annual_interest_rate,
      duration_months: Number(form.duration_months),
      first_repayment_date: form.first_repayment_date,
    });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="lg"
      title="Originate a loan"
      description="The vehicle must be assigned to the customer and ACTIVE; the assessment must be APPROVED and recent. Amounts and schedules are server-calculated."
    >
      <p className="mb-3 text-xs text-slate-500">
        The vehicle must be assigned to the customer and ACTIVE, and the credit assessment must be
        APPROVED, younger than {ASSESSMENT_AGE_DAYS} days and match the current profile. Amounts,
        schedule and affordability are server-calculated.
      </p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Customer">
            <Select
              value={form.customer}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  customer: e.target.value,
                  vehicle: "",
                  credit_assessment: "",
                }))
              }
              required
            >
              <option value="">Select a customer…</option>
              {(customers.data ?? []).map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.full_name} ({customer.currency})
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Vehicle"
            hint={
              form.customer === ""
                ? "Pick a customer first."
                : eligibleVehicles.length === 0
                  ? "No ACTIVE vehicles assigned to this customer."
                  : undefined
            }
          >
            <Select
              value={form.vehicle}
              onChange={(e) => update("vehicle", e.target.value)}
              disabled={form.customer === ""}
              required
            >
              <option value="">Select a vehicle…</option>
              {eligibleVehicles.map((vehicle) => (
                <option key={vehicle.id} value={vehicle.id}>
                  {vehicle.registration_number} · {vehicle.make} {vehicle.model_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Credit assessment"
            hint={
              form.customer === ""
                ? "Pick a customer first."
                : eligibleAssessments.length === 0
                  ? "No recent APPROVED assessments — run one on the customer page."
                  : undefined
            }
          >
            <Select
              value={form.credit_assessment}
              onChange={(e) => update("credit_assessment", e.target.value)}
              disabled={form.customer === ""}
              required
            >
              <option value="">Select an assessment…</option>
              {eligibleAssessments.map((assessment) => (
                <option key={assessment.id} value={assessment.id}>
                  Score {assessment.score} · {assessment.risk_band} ·{" "}
                  {new Date(assessment.created_at).toLocaleDateString()}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Principal amount" hint={selectedCustomer ? `In ${selectedCustomer.currency}` : undefined}>
            <Input
              type="number"
              min={0.01}
              step="0.01"
              value={form.principal_amount}
              onChange={(e) => update("principal_amount", e.target.value)}
              required
            />
          </Field>
          <Field label="Annual interest rate (%)" hint="Flat simple interest, e.g. 18.00">
            <Input
              type="number"
              min={0}
              max={100}
              step="0.01"
              value={form.annual_interest_rate}
              onChange={(e) => update("annual_interest_rate", e.target.value)}
              required
            />
          </Field>
          <Field label="Duration (months)">
            <Input
              type="number"
              min={1}
              max={120}
              value={form.duration_months}
              onChange={(e) => update("duration_months", e.target.value)}
              required
            />
          </Field>
          <Field label="First repayment date" hint="Within the next 90 days.">
            <Input
              type="date"
              value={form.first_repayment_date}
              onChange={(e) => update("first_repayment_date", e.target.value)}
              required
            />
          </Field>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button type="submit" loading={createLoan.isPending} className="flex-1">
            Create pending loan
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function LoansPage() {
  const { user } = useAuth();
  const isStaff = canManage(user);
  const [showCreate, setShowCreate] = useState(false);

  const loans = useQuery({
    queryKey: ["loans"],
    queryFn: () => listAll<Loan>("/loans/"),
  });

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
    enabled: isStaff,
  });
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => listAll<Vehicle>("/vehicles/"),
    enabled: isStaff,
  });

  const customerById = useMemo(
    () => new Map((customers.data ?? []).map((c) => [c.id, c])),
    [customers.data],
  );
  const vehicleById = useMemo(
    () => new Map((vehicles.data ?? []).map((v) => [v.id, v])),
    [vehicles.data],
  );

  return (
    <>
      <PageHeader
        title="Loans"
        subtitle={
          isStaff
            ? "Origination, schedules and lifecycle across the portfolio."
            : "Your financing agreements and repayment schedules."
        }
        actions={
          isStaff && (
            <Button variant="secondary" onClick={() => setShowCreate(true)}>
              Originate loan
            </Button>
          )
        }
      />

      {isStaff && <OriginationDialog open={showCreate} onClose={() => setShowCreate(false)} />}

      <Card>
        {loans.isLoading ? (
          <Spinner />
        ) : loans.isError ? (
          <p className="text-sm text-red-600">Could not load loans.</p>
        ) : loans.data?.length === 0 ? (
          <EmptyState>No loans yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Loan</th>
                  <th>Principal</th>
                  <th>Monthly</th>
                  <th>Outstanding</th>
                  <th>Term</th>
                  <th>Status</th>
                  {isStaff && <th>Customer</th>}
                </tr>
              </thead>
              <tbody>
                {(loans.data ?? []).map((loan) => (
                  <tr key={loan.id}>
                    <td>
                      <Link
                        to={`/loans/${loan.id}`}
                        className="font-mono text-xs font-medium text-indigo-600 hover:underline"
                      >
                        {loan.id.slice(0, 8)}…
                      </Link>
                      <span className="block text-xs text-slate-500">
                        {vehicleById.get(loan.vehicle)?.registration_number ??
                          "vehicle " + loan.vehicle.slice(0, 8) + "…"}
                      </span>
                    </td>
                    <td>{money(loan.principal_amount, loan.currency)}</td>
                    <td>{money(loan.monthly_repayment, loan.currency)}</td>
                    <td>
                      {money(loan.outstanding_balance, loan.currency)}
                    </td>
                    <td className="text-slate-500">
                      {loan.duration_months} mo @ {loan.annual_interest_rate}%
                    </td>
                    <td>
                      <Badge tone={loanTone(loan.status)}>{loan.status}</Badge>
                      <span className="mt-0.5 block text-xs text-slate-400">
                        {loan.status === "ACTIVE" && loan.activated_at
                          ? `activated ${relativeTime(loan.activated_at)}`
                          : `created ${relativeTime(loan.created_at)}`}
                      </span>
                    </td>
                    {isStaff && (
                      <td className="text-slate-500">
                        {customerById.get(loan.customer)?.full_name ?? loan.customer.slice(0, 8) + "…"}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
