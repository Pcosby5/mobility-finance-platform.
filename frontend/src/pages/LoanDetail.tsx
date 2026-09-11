import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { canManage, useAuth } from "@/auth/AuthContext";
import { PayNowDialog } from "@/components/PayNowDialog";
import { Badge, Button, Card, EmptyState, FormError, PageHeader, Spinner } from "@/components/ui";
import { api, apiErrorMessage, listAll } from "@/lib/api";
import { date, dateTime, loanTone, money } from "@/lib/format";
import type { CustomerProfile, Installment, Loan, Vehicle } from "@/types/api";

function compactId(id: string): string {
  return id.slice(0, 8);
}

function nextInstallment(installments: Installment[] | undefined): Installment | undefined {
  if (!installments?.length) return undefined;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return (
    installments.find((installment) => new Date(installment.due_date).getTime() >= today.getTime()) ??
    installments.at(-1)
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded-3xl border border-[color:var(--line-soft)] bg-[color:var(--soft-bg)] p-4 sm:p-5">
      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-faint)]">
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold tracking-tight text-[color:var(--text-strong)] sm:text-2xl">
        {value}
      </p>
      {detail && <p className="mt-1 text-xs text-[color:var(--text-muted)]">{detail}</p>}
    </div>
  );
}

function DetailItem({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-faint)]">
        {label}
      </dt>
      <dd className="mt-1 text-sm text-[color:var(--text-main)]">{children}</dd>
    </div>
  );
}

export function LoanDetailPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const isStaff = canManage(user);
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [showPay, setShowPay] = useState(false);

  const loan = useQuery({
    queryKey: ["loans", id],
    queryFn: () => api.get<Loan>(`/loans/${id}/`).then((r) => r.data),
  });

  const installments = useQuery({
    queryKey: ["loans", id, "installments"],
    queryFn: () => listAll<Installment>(`/loans/${id}/installments/`),
  });

  const customer = useQuery({
    queryKey: ["customers", loan.data?.customer],
    queryFn: () =>
      api.get<CustomerProfile>(`/customers/${loan.data!.customer}/`).then((r) => r.data),
    enabled: isStaff && loan.data?.customer != null,
  });

  const vehicle = useQuery({
    queryKey: ["vehicles", loan.data?.vehicle],
    queryFn: () => api.get<Vehicle>(`/vehicles/${loan.data!.vehicle}/`).then((r) => r.data),
    enabled: loan.data?.vehicle != null,
  });

  const transition = useMutation({
    mutationFn: (action: "activate" | "cancel") =>
      api.post<Loan>(`/loans/${id}/${action}/`, {}).then((r) => r.data),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["loans"] });
    },
    onError: (err) => setActionError(apiErrorMessage(err)),
  });

  if (loan.isLoading) return <Spinner className="mt-8" />;
  if (loan.isError) {
    return (
      <>
        <PageHeader title="Loan" />
        <Card>
          <p className="text-sm text-red-600">
            Could not load this loan. It may not exist or you lack access.
          </p>
        </Card>
      </>
    );
  }

  const data = loan.data!;
  const showActions = isStaff && data.status === "PENDING";
  const linkedVehicle = vehicle.data;
  const linkedCustomer = customer.data;
  const nextDue = nextInstallment(installments.data);
  const loanTitle = linkedVehicle
    ? `${linkedVehicle.make} ${linkedVehicle.model_name} Financing`
    : `Loan ${compactId(data.id)}`;
  const loanSubtitleParts = [
    linkedVehicle?.registration_number,
    linkedCustomer?.full_name,
    `Loan ${compactId(data.id)}`,
  ].filter(Boolean);

  return (
    <>
      <PageHeader
        title={loanTitle}
        subtitle={loanSubtitleParts.join(" · ")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={loanTone(data.status)}>{data.status}</Badge>
            {data.status === "ACTIVE" && <Button onClick={() => setShowPay(true)}>Pay now</Button>}
          </div>
        }
      />

      <PayNowDialog
        open={showPay}
        onClose={() => setShowPay(false)}
        loan={data}
      />

      <div className="grid gap-5">
        <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 xl:grid-cols-4">
          <Metric
            label="Outstanding balance"
            value={money(data.outstanding_balance, data.currency)}
            detail={data.status === "ACTIVE" ? "Live principal and interest balance" : "Set on activation"}
          />
          <Metric
            label="Monthly payment"
            value={money(data.monthly_repayment, data.currency)}
            detail={`Final payment ${money(data.final_repayment, data.currency)}`}
          />
          <Metric
            label="Next due date"
            value={nextDue ? date(nextDue.due_date) : date(data.first_repayment_date)}
            detail={nextDue ? `Installment ${nextDue.number}` : "Schedule pending"}
          />
          <Metric
            label="Term"
            value={`${data.duration_months} months`}
            detail={`${data.annual_interest_rate}% flat simple interest`}
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr] xl:gap-5">
        <Card title="Loan terms">
          <FormError message={actionError} />
          <dl className="grid gap-x-5 gap-y-5 sm:grid-cols-2">
            <DetailItem label="Principal">
              {money(data.principal_amount, data.currency)}
            </DetailItem>
            <DetailItem label="Interest">
                {data.annual_interest_rate}% flat · {money(data.total_interest, data.currency)}
            </DetailItem>
            <DetailItem label="Total repayable">
              {money(data.total_repayable, data.currency)}
            </DetailItem>
            <DetailItem label="Outstanding">
              {money(data.outstanding_balance, data.currency)}
            </DetailItem>
            <DetailItem label="Monthly / final">
                {money(data.monthly_repayment, data.currency)} /{" "}
                {money(data.final_repayment, data.currency)}
            </DetailItem>
            <DetailItem label="Term">
                {data.duration_months} months · first {date(data.first_repayment_date)}
            </DetailItem>
            <DetailItem label="Policy">
              <span className="font-mono text-xs text-[color:var(--text-muted)]">
                {data.policy_version ?? "—"}
              </span>
            </DetailItem>
            <DetailItem label="Timeline">
              <span className="text-xs text-[color:var(--text-muted)]">
                created {dateTime(data.created_at)}
                {data.activated_at ? ` · activated ${dateTime(data.activated_at)}` : ""}
                {data.cancelled_at ? ` · cancelled ${dateTime(data.cancelled_at)}` : ""}
              </span>
            </DetailItem>
            <div className="sm:col-span-2">
              <DetailItem label="Vehicle">
                {vehicle.data ? (
                  <Link to={`/vehicles/${vehicle.data.id}`} className="font-semibold text-blue-600 hover:underline">
                    {vehicle.data.registration_number} · {vehicle.data.make} {vehicle.data.model_name}
                  </Link>
                ) : (
                  <span className="font-mono text-xs">{compactId(data.vehicle)}…</span>
                )}
              </DetailItem>
            </div>
            {isStaff && customer.data && (
              <div className="sm:col-span-2">
                <DetailItem label="Customer">
                  <Link
                    to={`/customers/${customer.data.id}`}
                    className="font-semibold text-blue-600 hover:underline"
                  >
                    {customer.data.full_name}
                  </Link>
                </DetailItem>
              </div>
            )}
          </dl>

          {showActions && (
            <div className="mt-4 flex gap-2 border-t border-slate-100 pt-4">
              <Button loading={transition.isPending} onClick={() => transition.mutate("activate")}>
                Activate
              </Button>
              <Button
                variant="danger"
                loading={transition.isPending}
                onClick={() => transition.mutate("cancel")}
              >
                Cancel loan
              </Button>
            </div>
          )}
        </Card>

        <Card title="Repayment schedule">
          {installments.isLoading ? (
            <Spinner />
          ) : installments.isError ? (
            <p className="text-sm text-red-600">Could not load the schedule.</p>
          ) : installments.data?.length === 0 ? (
            <EmptyState>No installments.</EmptyState>
          ) : (
            <div className="max-h-[70svh] overflow-y-auto overflow-x-auto rounded-3xl border border-[color:var(--line-soft)] sm:max-h-[34rem]">
              <table className="data-table">
                <thead>
                  <tr className="sticky top-0 z-[1]">
                    <th>#</th>
                    <th>Due</th>
                    <th className="text-right">Principal</th>
                    <th className="text-right">Interest</th>
                    <th className="text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {(installments.data ?? []).map((installment) => (
                    <tr key={installment.id}>
                      <td className="text-[color:var(--text-muted)]">{installment.number}</td>
                      <td>{date(installment.due_date)}</td>
                      <td className="text-right tabular-nums">{money(installment.principal_due)}</td>
                      <td className="text-right tabular-nums">{money(installment.interest_due)}</td>
                      <td className="text-right font-semibold tabular-nums text-[color:var(--text-strong)]">
                        {money(installment.amount_due, data.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        </div>

        {data.origination_snapshot && (
          <Card title="Audit details" className="rounded-3xl">
            <details>
              <summary className="cursor-pointer text-sm font-semibold text-blue-600">
                Show stored origination inputs
              </summary>
              <pre className="mt-4 max-h-72 overflow-auto rounded-2xl bg-[color:var(--code-bg)] p-4 font-mono text-xs leading-6 text-[color:var(--text-muted)] ring-1 ring-[color:var(--line-soft)]">
                {JSON.stringify(data.origination_snapshot, null, 2)}
              </pre>
            </details>
          </Card>
        )}
      </div>
    </>
  );
}
