import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { canManage, useAuth } from "@/auth/AuthContext";
import { Badge, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { listAll } from "@/lib/api";
import { loanTone, money, relativeTime, severityTone } from "@/lib/format";
import type { Alert, CustomerProfile, Loan, Payment } from "@/types/api";

function StatCard({
  label,
  value,
  to,
}: {
  label: string;
  value: string | number | null | undefined;
  to: string;
}) {
  return (
    <Link
      to={to}
      className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-indigo-300 hover:shadow"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">
        {value === null || value === undefined ? "—" : value}
      </p>
    </Link>
  );
}

function LoanRows({ loans }: { loans: Loan[] }) {
  if (loans.length === 0) return <EmptyState>No loans yet.</EmptyState>;
  return (
    <ul className="divide-y divide-slate-100">
      {loans.slice(0, 5).map((loan) => (
        <li key={loan.id} className="flex items-center justify-between gap-3 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-900">
              {money(loan.principal_amount, loan.currency)} · {loan.duration_months} months
            </p>
            <p className="text-xs text-slate-500">
              {money(loan.monthly_repayment, loan.currency)}/mo ·{" "}
              {loan.status === "ACTIVE" && loan.activated_at
                ? `activated ${relativeTime(loan.activated_at)}`
                : `created ${relativeTime(loan.created_at)}`}
            </p>
          </div>
          <Badge tone={loanTone(loan.status)}>{loan.status}</Badge>
        </li>
      ))}
    </ul>
  );
}

function AlertRows({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) return <EmptyState>No open alerts. 🎉</EmptyState>;
  return (
    <ul className="divide-y divide-slate-100">
      {alerts.slice(0, 5).map((alert) => (
        <li key={alert.id} className="flex items-center justify-between gap-3 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-900">{alert.type}</p>
            <p className="truncate text-xs text-slate-500">{alert.message}</p>
          </div>
          <Badge tone={severityTone(alert.severity)}>{alert.severity}</Badge>
        </li>
      ))}
    </ul>
  );
}

/** Staff overview: portfolio counts across the whole platform. */
function StaffDashboard() {
  const loans = useQuery({ queryKey: ["loans", "all"], queryFn: () => listAll<Loan>("/loans/") });
  const payments = useQuery({
    queryKey: ["payments", "all"],
    queryFn: () => listAll<Payment>("/payments/"),
  });
  const alerts = useQuery({
    queryKey: ["alerts", "open"],
    queryFn: () => listAll<Alert>("/alerts/", { resolved: "false" }),
  });
  const customers = useQuery({
    queryKey: ["customers", "all"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
  });

  const openLoans = (loans.data ?? []).filter((loan) => loan.status === "ACTIVE");
  const pendingPayments = (payments.data ?? []).filter(
    (payment) => payment.status === "PENDING",
  );

  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Active loans" value={openLoans.length} to="/loans" />
        <StatCard label="Pending payments" value={pendingPayments.length} to="/payments" />
        <StatCard label="Open alerts" value={alerts.data?.length ?? null} to="/alerts" />
        <StatCard label="Customers" value={customers.data?.length ?? null} to="/customers" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card
          title="Recent loans"
          actions={
            <Link to="/loans" className="text-xs font-semibold text-indigo-600 hover:underline">
              View all
            </Link>
          }
        >
          {loans.isLoading ? (
            <Spinner />
          ) : loans.isError ? (
            <p className="text-sm text-red-600">Could not load loans.</p>
          ) : (
            <LoanRows loans={loans.data ?? []} />
          )}
        </Card>

        <Card
          title="Open alerts"
          actions={
            <Link to="/alerts" className="text-xs font-semibold text-indigo-600 hover:underline">
              View all
            </Link>
          }
        >
          {alerts.isLoading ? (
            <Spinner />
          ) : alerts.isError ? (
            <p className="text-sm text-red-600">Could not load alerts.</p>
          ) : (
            <AlertRows alerts={alerts.data ?? []} />
          )}
        </Card>
      </div>
    </>
  );
}

/** Customer overview: own profile, loans and vehicle alerts. */
function CustomerDashboard() {
  const profile = useQuery({
    queryKey: ["customers", "me"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
  });
  const loans = useQuery({ queryKey: ["loans", "me"], queryFn: () => listAll<Loan>("/loans/") });
  const alerts = useQuery({
    queryKey: ["alerts", "me-open"],
    queryFn: () => listAll<Alert>("/alerts/", { resolved: "false" }),
  });

  const myProfile = profile.data?.[0];
  const activeLoans = (loans.data ?? []).filter((loan) => loan.status === "ACTIVE");

  return (
    <>
      {!profile.isLoading && !myProfile && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          You have no financial profile yet — credit screening and loans need one.{" "}
          <Link to="/profile/new" className="font-semibold underline">
            Create your profile
          </Link>
        </div>
      )}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Monthly income"
          value={myProfile ? money(myProfile.monthly_income, myProfile.currency) : null}
          to="/profile"
        />
        <StatCard
          label="Active loans"
          value={activeLoans.length}
          to="/loans"
        />
        <StatCard
          label="Monthly repayment"
          value={
            activeLoans.length > 0
              ? money(
                  activeLoans.reduce(
                    (sum, loan) => sum + Number(loan.monthly_repayment),
                    0,
                  ),
                  myProfile?.currency,
                )
              : 0
          }
          to="/loans"
        />
        <StatCard label="Open alerts" value={alerts.data?.length ?? null} to="/alerts" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card
          title="My loans"
          actions={
            <Link to="/loans" className="text-xs font-semibold text-indigo-600 hover:underline">
              View all
            </Link>
          }
        >
          {loans.isLoading ? (
            <Spinner />
          ) : loans.isError ? (
            <p className="text-sm text-red-600">Could not load loans.</p>
          ) : (
            <LoanRows loans={loans.data ?? []} />
          )}
        </Card>

        <Card title="Alerts on my vehicles">
          {alerts.isLoading ? (
            <Spinner />
          ) : alerts.isError ? (
            <p className="text-sm text-red-600">Could not load alerts.</p>
          ) : (
            <AlertRows alerts={alerts.data ?? []} />
          )}
        </Card>
      </div>
    </>
  );
}

export function DashboardPage() {
  const { user } = useAuth();

  return (
    <>
      <PageHeader
        title={`Welcome${user?.first_name ? `, ${user.first_name}` : ""}`}
        subtitle={
          canManage(user)
            ? "Platform overview across customers, loans, payments and telematics."
            : "Your financing and vehicle overview."
        }
      />
      {canManage(user) ? <StaffDashboard /> : <CustomerDashboard />}
    </>
  );
}
