import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Dialog, Field, FormError, Input, Select } from "@/components/ui";
import { api, apiErrorMessage } from "@/lib/api";
import { money, paymentTone } from "@/lib/format";
import type {
  InitializedPayment,
  Loan,
  PaymentProvider,
  VerifiedPayment,
  Vehicle,
} from "@/types/api";

const PROVIDERS: PaymentProvider[] = ["PAYSTACK", "MOCK_MOMO"];
const POLL_MS = 3000;
const POLL_MAX_ATTEMPTS = 100; // ~5 minutes, then the payer can retry manually.

/**
 * Customer-facing payment dialog for one loan.
 *
 * Paystack flow: choose amount -> POST /payments/initialize/ -> the response
 * carries the hosted-checkout URL and the browser is redirected to it in the
 * same tab. Paystack returns to /payments?reference=… via callback_url, and
 * the webhook settles server-side regardless of the redirect.
 *
 * Simulated MoMo flow: there is no hosted checkout; the dialog stays open and
 * polls /payments/{ref}/verify/ so a dev-triggered callback resolves on screen.
 */
export function PayNowDialog({
  open,
  onClose,
  loan,
  loans,
  vehicleById,
  resume,
}: {
  open: boolean;
  onClose: () => void;
  /** Preselect and lock this loan (loan-detail "Pay now"). */
  loan?: Loan;
  /** Chooseable open loans (payments page). */
  loans?: Loan[];
  vehicleById?: Map<string, Vehicle>;
  /** Open directly on the status screen for an existing PENDING payment. */
  resume?: InitializedPayment | null;
}) {
  const queryClient = useQueryClient();

  const lockable = loan != null;
  const activeLoans = (loans ?? []).filter((candidate) => candidate.status === "ACTIVE");

  const [loanId, setLoanId] = useState(loan?.id ?? "");
  const [provider, setProvider] = useState<PaymentProvider>("PAYSTACK");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<InitializedPayment | null>(null);

  // Resume mode: show the status screen immediately and re-verify once so a
  // stored Paystack checkout link (or a settled outcome) shows up right away.
  useEffect(() => {
    if (!open || !resume) return;
    setCreated(resume);
    setNote(null);
    attemptsRef.current = 0;
    void checkNow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resume]);
  const [note, setNote] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const attemptsRef = useRef(0);
  const createdRef = useRef<InitializedPayment | null>(null);
  createdRef.current = created;

  const selectedLoan = loan ?? activeLoans.find((candidate) => candidate.id === loanId);

  // Poll verify only for the simulated provider (no hosted checkout to return
  // from). Paystack settles via webhook + the callback redirect re-verify.
  const shouldPoll = created?.status === "PENDING" && created.provider === "MOCK_MOMO";
  useEffect(() => {
    if (!open || !shouldPoll || !created) return;
    const reference = created.reference;
    const timer = window.setInterval(async () => {
      if (attemptsRef.current >= POLL_MAX_ATTEMPTS) {
        window.clearInterval(timer);
        setNote("Still pending — fire the simulator callback, then use “Check status now”.");
        return;
      }
      attemptsRef.current += 1;
      try {
        const { data } = await api.get<VerifiedPayment>(
          `/payments/${encodeURIComponent(reference)}/verify/`,
        );
        if (createdRef.current?.reference !== reference) return;
        setNote(data.detail);
        if (data.status !== "PENDING") {
          window.clearInterval(timer);
          setCreated(data);
          void queryClient.invalidateQueries({ queryKey: ["loans"] });
          void queryClient.invalidateQueries({ queryKey: ["payments"] });
        }
      } catch {
        // Provider hiccup: keep polling.
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [open, shouldPoll, created, queryClient]);

  function reset() {
    setLoanId(loan?.id ?? "");
    setProvider("PAYSTACK");
    setAmount("");
    setError(null);
    setCreated(null);
    setNote(null);
    setChecking(false);
    attemptsRef.current = 0;
  }

  function handleClose() {
    onClose();
    window.setTimeout(reset, 200);
  }

  async function checkNow() {
    if (!created) return;
    setChecking(true);
    try {
      const { data } = await api.get<VerifiedPayment>(
        `/payments/${encodeURIComponent(created.reference)}/verify/`,
      );
      setNote(data.detail);
      if (data.status !== "PENDING") {
        setCreated(data);
        void queryClient.invalidateQueries({ queryKey: ["loans"] });
        void queryClient.invalidateQueries({ queryKey: ["payments"] });
      }
    } catch (err) {
      setNote(apiErrorMessage(err));
    } finally {
      setChecking(false);
    }
  }

  const initialize = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post<InitializedPayment>("/payments/initialize/", payload).then((r) => r.data),
    onSuccess: (data) => {
      // The Paystack checkout session is the product here: send the payer to
      // it immediately in the same tab. Paystack returns to
      // /payments?reference=… (callback_url); the webhook settles server-side.
      if (data.checkout_url) {
        window.location.assign(data.checkout_url);
        return;
      }
      setCreated(data);
      setNote(
        data.provider === "PAYSTACK"
          ? "The provider did not return a checkout session — verify this payment or try again."
          : "Simulated charge created — waiting for the dev callback, polling below.",
      );
      attemptsRef.current = 0;
      void queryClient.invalidateQueries({ queryKey: ["payments"] });
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!loanId) return;
    initialize.mutate({
      loan_id: loanId,
      provider,
      ...(amount ? { amount } : {}),
    });
  }

  const settled = created != null && created.status !== "PENDING";

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title={created ? "Payment status" : "Pay a loan"}
      description={
        created
          ? undefined
          : "You will be redirected to the provider's secure checkout to complete the payment."
      }
    >
      {created ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-3">
            <div className="min-w-0">
              <p className="truncate font-mono text-xs text-slate-500">{created.reference}</p>
              <p className="mt-0.5 text-sm font-semibold text-slate-900">
                {money(created.amount, created.currency)} · {created.provider}
              </p>
            </div>
            <Badge tone={paymentTone(created.status)}>{created.status}</Badge>
          </div>

          {created.status === "PENDING" && (
            <div className="space-y-3">
              {created.checkout_url && (
                <a
                  href={created.checkout_url}
                  className="block w-full rounded-md bg-indigo-600 px-3 py-2 text-center text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
                >
                  Continue to checkout
                </a>
              )}
              <p className="text-sm text-slate-500">
                {note ?? "Waiting for the provider to confirm the payment…"}
              </p>
              <Button variant="secondary" loading={checking} onClick={checkNow} className="w-full">
                Check status now
              </Button>
            </div>
          )}

          {settled && created.status === "SUCCESS" && (
            <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700 ring-1 ring-inset ring-emerald-200">
              Payment successful — the loan balance has been updated.
            </p>
          )}

          {settled && created.status !== "SUCCESS" && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-inset ring-red-200">
              {created.failure_reason ?? "The payment did not complete."}
            </p>
          )}

          <div className="flex gap-2">
            {settled && created.status !== "SUCCESS" && (
              <Button
                variant="secondary"
                className="flex-1"
                onClick={() => {
                  setCreated(null);
                  setNote(null);
                  attemptsRef.current = 0;
                }}
              >
                Try again
              </Button>
            )}
            <Button
              variant={settled ? "primary" : "secondary"}
              onClick={handleClose}
              className="flex-1"
            >
              {settled ? "Done" : "Close"}
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <FormError message={error} />
          <Field label="Loan">
            <Select
              value={loanId}
              onChange={(e) => setLoanId(e.target.value)}
              disabled={lockable}
              required
            >
              <option value="">Select an ACTIVE loan…</option>
              {(lockable ? [loan] : activeLoans).map((candidate) => (
                <option key={candidate!.id} value={candidate!.id}>
                  {vehicleById?.get(candidate!.vehicle)?.registration_number ??
                    candidate!.id.slice(0, 8) + "…"}{" "}
                  · {money(candidate!.outstanding_balance, candidate!.currency)} outstanding
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Provider">
            <Select
              value={provider}
              onChange={(e) => setProvider(e.target.value as PaymentProvider)}
            >
              {PROVIDERS.map((name) => (
                <option key={name} value={name}>
                  {name === "PAYSTACK" ? "Paystack (card / mobile money)" : "Simulated MoMo (dev)"}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Amount"
            hint={
              selectedLoan
                ? `Leave blank to pay the full outstanding balance (${money(
                    selectedLoan.outstanding_balance,
                    selectedLoan.currency,
                  )}).`
                : "Leave blank for the full outstanding balance."
            }
          >
            <Input
              type="number"
              min={0.01}
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={selectedLoan ? selectedLoan.outstanding_balance : ""}
            />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" loading={initialize.isPending} className="flex-1">
              Continue to payment
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
