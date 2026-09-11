import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ProfileDialog } from "@/pages/CustomerProfileForm";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { api, apiErrorMessage, listAll } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { CreditAssessment, CustomerProfile } from "@/types/api";

function DecisionBadge({ assessment }: { assessment: CreditAssessment }) {
  const tone =
    assessment.decision === "APPROVED"
      ? "success"
      : assessment.decision === "REJECTED"
        ? "danger"
        : "warning";
  return <Badge tone={tone}>{assessment.decision}</Badge>;
}

export function CustomerDetailPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [showEdit, setShowEdit] = useState(false);

  const customer = useQuery({
    queryKey: ["customers", id],
    queryFn: () => api.get<CustomerProfile>(`/customers/${id}/`).then((r) => r.data),
  });

  const assessments = useQuery({
    queryKey: ["customers", id, "assessments"],
    queryFn: () => listAll<CreditAssessment>(`/customers/${id}/credit-assessments/`),
  });

  const runAssessment = useMutation({
    mutationFn: () => api.post(`/customers/${id}/credit-assessments/`).then((r) => r.data),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["customers", id, "assessments"] });
    },
    onError: (err) => setActionError(apiErrorMessage(err)),
  });

  if (customer.isLoading) return <Spinner className="mt-8" />;
  if (customer.isError) {
    return (
      <>
        <PageHeader title="Customer" />
        <Card>
          <p className="text-sm text-red-600">
            Could not load this customer. It may not exist or you lack access.
          </p>
        </Card>
      </>
    );
  }

  const profile = customer.data!;
  const assessmentList = assessments.data ?? [];

  return (
    <>
      <PageHeader
        title={profile.full_name}
        subtitle={`${profile.username} · ${profile.phone}${profile.email ? ` · ${profile.email}` : ""}`}
      />

      <ProfileDialog open={showEdit} onClose={() => setShowEdit(false)} profile={profile} />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card
          title="Financial profile"
          actions={
            <Button variant="secondary" onClick={() => setShowEdit(true)}>
              Edit
            </Button>
          }
        >
          <dl className="grid gap-x-4 gap-y-4 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Employment</dt>
              <dd className="mt-0.5">
                {profile.employment_status}
                {profile.employment_duration_months !== null &&
                  ` · ${profile.employment_duration_months} mo`}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Currency</dt>
              <dd className="mt-0.5">{profile.currency}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Monthly income</dt>
              <dd className="mt-0.5">{money(profile.monthly_income, profile.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Existing debt</dt>
              <dd className="mt-0.5">{money(profile.existing_debt, profile.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Monthly debt repayment
              </dt>
              <dd className="mt-0.5">{money(profile.monthly_debt_repayment, profile.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Member since</dt>
              <dd className="mt-0.5">{dateTime(profile.created_at)}</dd>
            </div>
          </dl>
        </Card>

        <Card
          title="Credit assessments"
          actions={
            <Button
              variant="secondary"
              loading={runAssessment.isPending}
              onClick={() => runAssessment.mutate()}
            >
              Run assessment
            </Button>
          }
        >
          <FormErrorSlot message={actionError} />
          {assessments.isLoading ? (
            <Spinner />
          ) : assessments.isError ? (
            <p className="text-sm text-red-600">Could not load assessments.</p>
          ) : assessmentList.length === 0 ? (
            <EmptyState>No assessments yet — run the first one.</EmptyState>
          ) : (
            <ul className="space-y-3">
              {assessmentList.map((assessment) => (
                <li
                  key={assessment.id}
                  className="rounded-lg border border-slate-200 p-3 text-sm"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-900">
                      Score {assessment.score} · {assessment.risk_band} risk
                    </span>
                    <DecisionBadge assessment={assessment} />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {dateTime(assessment.created_at)}
                    {assessment.policy_version ? ` · policy ${assessment.policy_version}` : ""}
                  </p>
                  <ul className="mt-2 space-y-1">
                    {assessment.factors.map((factor, index) => (
                      <li key={index} className="text-xs text-slate-600">
                        {factor.summary}
                        {factor.points !== undefined && (
                          <span className="ml-1 text-slate-400">({factor.points > 0 ? "+" : ""}{factor.points})</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

function FormErrorSlot({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-inset ring-red-200"
    >
      {message}
    </p>
  );
}
