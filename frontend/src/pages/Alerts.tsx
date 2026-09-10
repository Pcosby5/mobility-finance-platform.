import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { canManage, useAuth } from "@/auth/AuthContext";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { api, apiErrorMessage, listAll } from "@/lib/api";
import { dateTime, relativeTime, severityTone } from "@/lib/format";
import type { Alert, AlertType, Vehicle } from "@/types/api";

const ALERT_TYPES: AlertType[] = ["GEOFENCE_EXIT", "SPEEDING", "LOW_BATTERY", "OFFLINE"];

export function AlertsPage() {
  const { user } = useAuth();
  const isStaff = canManage(user);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState<AlertType | "">("");
  const [resolved, setResolved] = useState<"open" | "resolved" | "all">("open");

  const alerts = useQuery({
    queryKey: ["alerts", { type, resolved }],
    queryFn: () =>
      listAll<Alert>("/alerts/", {
        ...(type ? { type } : {}),
        ...(resolved === "all" ? {} : { resolved: resolved === "resolved" ? "true" : "false" }),
      }),
  });

  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => listAll<Vehicle>("/vehicles/"),
  });

  const resolve = useMutation({
    mutationFn: (id: string) => api.post<Alert>(`/alerts/${id}/resolve/`, {}).then((r) => r.data),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const vehicleById = new Map((vehicles.data ?? []).map((vehicle) => [vehicle.id, vehicle]));

  return (
    <>
      <PageHeader
        title="Alerts"
        subtitle={
          isStaff
            ? "Geofence exits, speeding, low battery and offline vehicles across the fleet."
            : "Alerts on your vehicles. Condition alerts clear automatically when resolved."
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={type}
          onChange={(e) => setType(e.target.value as AlertType | "")}
          className="rounded-md border-0 bg-white px-3 py-2 text-sm shadow-sm ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-inset focus:ring-indigo-600"
        >
          <option value="">All types</option>
          {ALERT_TYPES.map((alertType) => (
            <option key={alertType} value={alertType}>
              {alertType.replace("_", " ")}
            </option>
          ))}
        </select>
        <div className="flex gap-1 rounded-lg bg-slate-200/60 p-1 text-sm font-medium">
          {(["open", "resolved", "all"] as const).map((key) => (
            <button
              key={key}
              onClick={() => setResolved(key)}
              className={
                resolved === key
                  ? "rounded-md bg-white px-3 py-1.5 capitalize text-slate-900 shadow-sm"
                  : "rounded-md px-3 py-1.5 capitalize text-slate-600 hover:text-slate-900"
              }
            >
              {key}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-inset ring-red-200"
        >
          {error}
        </p>
      )}

      <Card>
        {alerts.isLoading ? (
          <Spinner />
        ) : alerts.isError ? (
          <p className="text-sm text-red-600">Could not load alerts.</p>
        ) : alerts.data?.length === 0 ? (
          <EmptyState>No {resolved === "all" ? "" : resolved + " "}alerts.</EmptyState>
        ) : (
          <ul className="divide-y divide-slate-100">
            {(alerts.data ?? []).map((alert) => {
              const vehicle = vehicleById.get(alert.vehicle);
              return (
                <li key={alert.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge tone={severityTone(alert.severity)}>{alert.type.replace("_", " ")}</Badge>
                      <span className="text-xs text-slate-400" title={dateTime(alert.created_at)}>
                        {relativeTime(alert.created_at)}
                      </span>
                      {alert.resolved_at && (
                        <span className="text-xs text-emerald-600">
                          resolved {relativeTime(alert.resolved_at)}
                          {alert.resolved_by ? " by operator" : " automatically"}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-slate-900">{alert.message}</p>
                    <p className="text-xs text-slate-500">
                      Vehicle:{" "}
                      {vehicle ? (
                        <Link
                          to={`/vehicles/${vehicle.id}`}
                          className="text-indigo-600 hover:underline"
                        >
                          {vehicle.registration_number}
                        </Link>
                      ) : (
                        alert.vehicle.slice(0, 8) + "…"
                      )}
                    </p>
                  </div>
                  {isStaff && !alert.resolved_at && (
                    <Button
                      variant="secondary"
                      loading={resolve.isPending && resolve.variables === alert.id}
                      onClick={() => resolve.mutate(alert.id)}
                    >
                      Resolve
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
