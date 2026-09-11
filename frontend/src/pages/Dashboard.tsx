import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { canManage, useAuth } from "@/auth/AuthContext";
import { ProfileDialog } from "@/pages/CustomerProfileForm";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { listAll } from "@/lib/api";
import { loanTone, money, relativeTime, severityTone } from "@/lib/format";
import type { Alert, CustomerProfile, Loan, Payment } from "@/types/api";

function StatCard({
  label,
  value,
  to,
  accent = "slate",
  icon,
  detail,
}: {
  label: string;
  value: string | number | null | undefined;
  to: string;
  accent?: "slate" | "blue" | "emerald" | "amber";
  icon: ReactNode;
  detail: string;
}) {
  const accents = {
    slate: {
      icon: "metric-icon-slate",
      glow: "bg-slate-400/12",
    },
    blue: {
      icon: "metric-icon-blue",
      glow: "bg-blue-400/12",
    },
    emerald: {
      icon: "metric-icon-emerald",
      glow: "bg-emerald-400/12",
    },
    amber: {
      icon: "metric-icon-amber",
      glow: "bg-amber-400/12",
    },
  } as const;

  return (
    <Link
      to={to}
      className="metric-link group block"
    >
      <span
        className={`absolute -right-7 -top-7 size-24 rounded-full blur-2xl ${accents[accent].glow}`}
      />
      <div className="relative flex items-start justify-between gap-4">
        <div>
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-faint)]">
            {label}
          </p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-[color:var(--text-strong)]">
            {value === null || value === undefined ? "..." : value}
          </p>
        </div>
        <span
          className={`grid size-10 shrink-0 place-items-center rounded-2xl ring-1 ring-inset transition duration-300 group-hover:scale-105 sm:size-11 ${accents[accent].icon}`}
        >
          {icon}
        </span>
      </div>
      <div className="relative mt-4 flex items-center justify-between gap-3">
        <p className="text-xs font-medium text-[color:var(--text-muted)]">{detail}</p>
        <span className="text-sm text-[color:var(--text-faint)] transition group-hover:translate-x-0.5">
          →
        </span>
      </div>
    </Link>
  );
}

function LoansIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 8h10M7 12h6m-6 4h4" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 3h12a2 2 0 0 1 2 2v14l-3-2-3 2-3-2-3 2-3-2V5a2 2 0 0 1 2-2Z" />
    </svg>
  );
}

function PaymentsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="3" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M7 15h3" />
    </svg>
  );
}

function AlertsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.3 4.2 2.9 17a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" />
    </svg>
  );
}

function CustomersIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 19a4 4 0 0 0-8 0" />
      <circle cx="12" cy="9" r="3" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 18a3.5 3.5 0 0 0-3-3.4M4 18a3.5 3.5 0 0 1 3-3.4" />
    </svg>
  );
}

function IncomeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 19V5m0 14h16M8 15l3-4 3 2 4-7" />
    </svg>
  );
}

function LoanRows({ loans }: { loans: Loan[] }) {
  if (loans.length === 0) return <EmptyState>No loans yet.</EmptyState>;
  return (
    <ul className="divide-y divide-[color:var(--line-soft)]">
      {loans.slice(0, 5).map((loan) => (
        <li key={loan.id} className="flex items-center justify-between gap-3 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-[color:var(--text-strong)]">
              {money(loan.principal_amount, loan.currency)} · {loan.duration_months} months
            </p>
            <p className="text-xs text-[color:var(--text-muted)]">
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
  if (alerts.length === 0) return <EmptyState>No open alerts.</EmptyState>;
  return (
    <ul className="divide-y divide-[color:var(--line-soft)]">
      {alerts.slice(0, 5).map((alert) => (
        <li key={alert.id} className="flex items-center justify-between gap-3 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-[color:var(--text-strong)]">{alert.type}</p>
            <p className="truncate text-xs text-[color:var(--text-muted)]">{alert.message}</p>
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
      <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 xl:grid-cols-4">
        <StatCard
          label="Active loans"
          value={openLoans.length}
          to="/loans"
          accent="blue"
          icon={<LoansIcon />}
          detail="Live financing book"
        />
        <StatCard
          label="Pending payments"
          value={pendingPayments.length}
          to="/payments"
          accent="amber"
          icon={<PaymentsIcon />}
          detail="Awaiting provider outcome"
        />
        <StatCard
          label="Open alerts"
          value={alerts.data?.length ?? null}
          to="/alerts"
          accent="slate"
          icon={<AlertsIcon />}
          detail="Fleet exceptions"
        />
        <StatCard
          label="Customers"
          value={customers.data?.length ?? null}
          to="/customers"
          accent="emerald"
          icon={<CustomersIcon />}
          detail="Financial profiles"
        />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2 xl:gap-5">
        <Card
          title="Recent loans"
          actions={
            <Link to="/loans" className="text-xs font-semibold text-link hover:underline">
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
            <Link to="/alerts" className="text-xs font-semibold text-link hover:underline">
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
  const queryClient = useQueryClient();
  const [showProfile, setShowProfile] = useState(false);
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
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <span>
            You have no financial profile yet — credit screening and loans need one.
          </span>
          <Button variant="secondary" onClick={() => setShowProfile(true)}>
            Create your profile
          </Button>
        </div>
      )}
      <ProfileDialog
        open={showProfile}
        onClose={() => setShowProfile(false)}
        onSaved={() => queryClient.invalidateQueries({ queryKey: ["customers"] })}
      />
      <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 xl:grid-cols-4">
        <StatCard
          label="Monthly income"
          value={myProfile ? money(myProfile.monthly_income, myProfile.currency) : null}
          to="/profile"
          accent="emerald"
          icon={<IncomeIcon />}
          detail="Profile baseline"
        />
        <StatCard
          label="Active loans"
          value={activeLoans.length}
          to="/loans"
          accent="blue"
          icon={<LoansIcon />}
          detail="Current agreements"
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
          accent="amber"
          icon={<PaymentsIcon />}
          detail="Scheduled obligation"
        />
        <StatCard
          label="Open alerts"
          value={alerts.data?.length ?? null}
          to="/alerts"
          accent="slate"
          icon={<AlertsIcon />}
          detail="Vehicle exceptions"
        />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2 xl:gap-5">
        <Card
          title="My loans"
          actions={
            <Link to="/loans" className="text-xs font-semibold text-link hover:underline">
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
