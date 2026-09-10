import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { canManage, useAuth } from "@/auth/AuthContext";
import { PayNowDialog } from "@/components/PayNowDialog";
import { Badge, Button, Card, EmptyState, FormError, PageHeader, Spinner } from "@/components/ui";
import { api, apiErrorMessage, listAll } from "@/lib/api";
import { date, dateTime, loanTone, money } from "@/lib/format";
import type { CustomerProfile, Installment, Loan, Vehicle } from "@/types/api";

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

  return (
    <>
      <PageHeader
        title={`Loan ${data.id.slice(0, 8)}…`}
        subtitle={
          data.status === "PENDING"
            ? "Pending — activation rechecks eligibility and affordability before setting the balance."
            : "Flat simple interest with a server-calculated schedule."
        }
        actions={
          data.status === "ACTIVE" && (
            <Button onClick={() => setShowPay(true)}>Pay now</Button>
          )
        }
      />

      <PayNowDialog
        open={showPay}
        onClose={() => setShowPay(false)}
        loan={data}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Terms" actions={<Badge tone={loanTone(data.status)}>{data.status}</Badge>}>
          <FormError message={actionError} />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Principal</dt>
              <dd className="mt-0.5">{money(data.principal_amount, data.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Interest</dt>
              <dd className="mt-0.5">
                {data.annual_interest_rate}% flat · {money(data.total_interest, data.currency)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Total repayable</dt>
              <dd className="mt-0.5">{money(data.total_repayable, data.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Outstanding</dt>
              <dd className="mt-0.5">{money(data.outstanding_balance, data.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Monthly / final</dt>
              <dd className="mt-0.5">
                {money(data.monthly_repayment, data.currency)} /{" "}
                {money(data.final_repayment, data.currency)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Term</dt>
              <dd className="mt-0.5">
                {data.duration_months} months · first {date(data.first_repayment_date)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Policy</dt>
              <dd className="mt-0.5 text-xs text-slate-500">{data.policy_version ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Timeline</dt>
              <dd className="mt-0.5 text-xs text-slate-500">
                created {dateTime(data.created_at)}
                {data.activated_at ? ` · activated ${dateTime(data.activated_at)}` : ""}
                {data.cancelled_at ? ` · cancelled ${dateTime(data.cancelled_at)}` : ""}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-xs uppercase tracking-wide text-slate-500">Vehicle</dt>
              <dd className="mt-0.5">
                {vehicle.data ? (
                  <Link to={`/vehicles/${vehicle.data.id}`} className="text-indigo-600 hover:underline">
                    {vehicle.data.registration_number} · {vehicle.data.make} {vehicle.data.model_name}
                  </Link>
                ) : (
                  <span className="font-mono text-xs">{data.vehicle.slice(0, 8)}…</span>
                )}
              </dd>
            </div>
            {isStaff && customer.data && (
              <div className="col-span-2">
                <dt className="text-xs uppercase tracking-wide text-slate-500">Customer</dt>
                <dd className="mt-0.5">
                  <Link
                    to={`/customers/${customer.data.id}`}
                    className="text-indigo-600 hover:underline"
                  >
                    {customer.data.full_name}
                  </Link>
                </dd>
              </div>
            )}
            {data.origination_snapshot && (
              <div className="col-span-2">
                <dt className="text-xs uppercase tracking-wide text-slate-500">
                  Origination snapshot
                </dt>
                <dd className="mt-1">
                  <details>
                    <summary className="cursor-pointer text-xs font-medium text-indigo-600">
                      Show stored inputs
                    </summary>
                    <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-slate-50 p-2 font-mono text-xs text-slate-700">
                      {JSON.stringify(data.origination_snapshot, null, 2)}
                    </pre>
                  </details>
                </dd>
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
            <div className="max-h-[32rem] overflow-y-auto overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="py-2 pr-4 font-medium">#</th>
                    <th className="py-2 pr-4 font-medium">Due</th>
                    <th className="py-2 pr-4 font-medium">Principal</th>
                    <th className="py-2 pr-4 font-medium">Interest</th>
                    <th className="py-2 pr-4 font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(installments.data ?? []).map((installment) => (
                    <tr key={installment.id} className="hover:bg-slate-50">
                      <td className="py-2 pr-4 text-slate-500">{installment.number}</td>
                      <td className="py-2 pr-4">{date(installment.due_date)}</td>
                      <td className="py-2 pr-4">{money(installment.principal_due)}</td>
                      <td className="py-2 pr-4">{money(installment.interest_due)}</td>
                      <td className="py-2 pr-4 font-medium">
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
    </>
  );
}
