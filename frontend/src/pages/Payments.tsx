import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { canManage, useAuth } from "@/auth/AuthContext";
import { PayNowDialog } from "@/components/PayNowDialog";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  FormError,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { useMutation } from "@tanstack/react-query";
import { api, apiErrorMessage, listAll } from "@/lib/api";
import { dateTime, money, paymentTone, relativeTime } from "@/lib/format";
import type { Loan, Payment, Vehicle, VerifiedPayment, WebhookEvent } from "@/types/api";

const WEBHOOK_TONES: Record<WebhookEvent["status"], "info" | "success" | "neutral"> = {
  RECEIVED: "info",
  PROCESSED: "success",
  IGNORED: "neutral",
};

function LedgerTable({
  payments,
  loanById,
  vehicleById,
  onResume,
}: {
  payments: Payment[];
  loanById: Map<string, Loan>;
  vehicleById: Map<string, Vehicle>;
  onResume: (payment: Payment) => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [rowNote, setRowNote] = useState<{ reference: string; note: string } | null>(null);

  const verify = useMutation({
    mutationFn: (reference: string) =>
      api
        .get<VerifiedPayment>(`/payments/${encodeURIComponent(reference)}/verify/`)
        .then((r) => r.data),
    onSuccess: (data) => {
      setError(null);
      setRowNote({ reference: data.reference, note: data.detail });
      queryClient.invalidateQueries({ queryKey: ["payments"] });
      queryClient.invalidateQueries({ queryKey: ["loans"] });
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  return (
    <>
      <FormError message={error} />
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Reference</th>
              <th>Loan</th>
              <th>Provider</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {payments.map((payment) => (
              <tr key={payment.id}>
                <td className="font-mono text-xs">{payment.reference}</td>
                <td>
                  <Link
                    to={`/loans/${payment.loan}`}
                    className="font-mono text-xs text-indigo-600 hover:underline"
                  >
                    {vehicleById.get(loanById.get(payment.loan)?.vehicle ?? "")
                      ?.registration_number ??
                      payment.loan.slice(0, 8) + "…"}
                  </Link>
                </td>
                <td>{payment.provider}</td>
                <td>{money(payment.amount, payment.currency)}</td>
                <td>
                  <Badge tone={paymentTone(payment.status)}>{payment.status}</Badge>
                  {payment.failure_reason && (
                    <span className="mt-0.5 block text-xs text-red-600">
                      {payment.failure_reason}
                    </span>
                  )}
                  {rowNote?.reference === payment.reference && (
                    <span className="mt-0.5 block text-xs text-slate-500">{rowNote.note}</span>
                  )}
                </td>
                <td className="text-slate-500" title={dateTime(payment.created_at)}>
                  {relativeTime(payment.created_at)}
                </td>
                <td className="text-right">
                  {payment.status === "PENDING" && (
                    <>
                      {payment.provider === "PAYSTACK" && (
                        <Button variant="ghost" onClick={() => onResume(payment)}>
                          Resume checkout
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        loading={verify.isPending && verify.variables === payment.reference}
                        onClick={() => verify.mutate(payment.reference)}
                      >
                        Verify
                      </Button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function WebhookTable({ events }: { events: WebhookEvent[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Provider</th>
            <th>Event</th>
            <th>Delivery ref</th>
            <th>Status</th>
            <th>Note</th>
            <th>Received</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.id}>
              <td>{event.provider}</td>
              <td className="font-mono text-xs">{event.event_type}</td>
              <td className="font-mono text-xs">{event.delivery_reference}</td>
              <td>
                <Badge tone={WEBHOOK_TONES[event.status]}>{event.status}</Badge>
              </td>
              <td className="text-xs text-slate-500">{event.note}</td>
              <td className="text-slate-500" title={dateTime(event.received_at)}>
                {relativeTime(event.received_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PaymentsPage() {
  const { user } = useAuth();
  const isStaff = canManage(user);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [view, setView] = useState<"ledger" | "webhooks">("ledger");
  const [showPay, setShowPay] = useState(false);
  const [resumePayment, setResumePayment] = useState<Payment | null>(null);
  const [returnNote, setReturnNote] = useState<string | null>(null);
  const handledReferenceRef = useRef<string | null>(null);

  // Returning from Paystack's hosted checkout lands here with ?reference=…
  // Re-verify once so the ledger reflects settlement immediately, then clean
  // the URL. (Settlement itself is webhook/verify-driven server-side.)
  const checkoutReference = searchParams.get("reference");
  useEffect(() => {
    if (!checkoutReference || handledReferenceRef.current === checkoutReference) return;
    handledReferenceRef.current = checkoutReference;
    api
      .get<Payment>(`/payments/${encodeURIComponent(checkoutReference)}/verify/`)
      .then(({ data }) => {
        setReturnNote(
          `Returned from checkout — payment ${data.reference} is ${data.status}.`,
        );
        void queryClient.invalidateQueries({ queryKey: ["payments"] });
        void queryClient.invalidateQueries({ queryKey: ["loans"] });
      })
      .catch((err) => setReturnNote(apiErrorMessage(err)))
      .finally(() => setSearchParams({}, { replace: true }));
  }, [checkoutReference, queryClient, setSearchParams]);

  const payments = useQuery({
    queryKey: ["payments"],
    queryFn: () => listAll<Payment>("/payments/"),
  });

  const webhookEvents = useQuery({
    queryKey: ["webhook-events"],
    queryFn: () => listAll<WebhookEvent>("/payments/webhook-events/"),
    enabled: isStaff && view === "webhooks",
  });

  // Loans power the pay dialog (customers are scoped server-side) and ledger labels.
  const loans = useQuery({
    queryKey: ["loans"],
    queryFn: () => listAll<Loan>("/loans/"),
  });
  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => listAll<Vehicle>("/vehicles/"),
    enabled: isStaff,
  });

  const loanById = new Map((loans.data ?? []).map((loan) => [loan.id, loan]));
  const vehicleById = new Map((vehicles.data ?? []).map((vehicle) => [vehicle.id, vehicle]));

  return (
    <>
      <PageHeader
        title="Payments"
        subtitle={
          isStaff
            ? "Append-only ledger: only verified provider outcomes move balances."
            : "Pay an active loan and track your payments. Only verified provider outcomes settle."
        }
        actions={<Button onClick={() => setShowPay(true)}>Pay a loan</Button>}
      />

      {returnNote && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-800">
          <span>{returnNote}</span>
          <button
            onClick={() => setReturnNote(null)}
            className="text-xs font-semibold text-sky-700 hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {isStaff && (
        <div className="mb-4 flex w-fit gap-1 rounded-lg bg-slate-200/60 p-1 text-sm font-medium">
          {(
            [
              ["ledger", "Ledger"],
              ["webhooks", "Webhook events"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setView(key)}
              className={
                view === key
                  ? "rounded-md bg-white px-3 py-1.5 text-slate-900 shadow-sm"
                  : "rounded-md px-3 py-1.5 text-slate-600 hover:text-slate-900"
              }
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <Card>
        {view === "ledger" ? (
          payments.isLoading ? (
            <Spinner />
          ) : payments.isError ? (
            <p className="text-sm text-red-600">Could not load payments.</p>
          ) : payments.data?.length === 0 ? (
            <EmptyState>No payments yet — pay an active loan to get started.</EmptyState>
          ) : (
            <LedgerTable
              payments={payments.data ?? []}
              loanById={loanById}
              vehicleById={vehicleById}
              onResume={setResumePayment}
            />
          )
        ) : webhookEvents.isLoading ? (
          <Spinner />
        ) : webhookEvents.isError ? (
          <p className="text-sm text-red-600">Could not load webhook events.</p>
        ) : webhookEvents.data?.length === 0 ? (
          <EmptyState>No webhook deliveries recorded.</EmptyState>
        ) : (
          <WebhookTable events={webhookEvents.data ?? []} />
        )}
      </Card>

      <PayNowDialog
        open={showPay || resumePayment != null}
        onClose={() => {
          setShowPay(false);
          setResumePayment(null);
        }}
        loans={loans.data ?? []}
        vehicleById={vehicleById}
        resume={resumePayment}
      />
    </>
  );
}
