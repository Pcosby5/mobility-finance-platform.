import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { canManage, useAuth } from "@/auth/AuthContext";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  FormError,
  Input,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { api, apiErrorMessage, listAll } from "@/lib/api";
import {
  connectivityTone,
  dateTime,
  movementTone,
  orDash,
  osmLink,
  vehicleTone,
} from "@/lib/format";
import type { CustomerProfile, TelemetryRecord, Vehicle, VehicleStatus } from "@/types/api";

const VEHICLE_STATUSES: VehicleStatus[] = ["ACTIVE", "MAINTENANCE", "RETIRED"];

function TelemetryTable({ vehicleId }: { vehicleId: string }) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [ordering, setOrdering] = useState("-recorded_at");

  const telemetry = useQuery({
    queryKey: ["vehicles", vehicleId, "telemetry", { start, end, ordering }],
    queryFn: () =>
      listAll<TelemetryRecord>(`/vehicles/${vehicleId}/telemetry/`, {
        ...(start ? { start: new Date(start).toISOString() } : {}),
        ...(end ? { end: new Date(end).toISOString() } : {}),
        ordering,
      }),
  });

  return (
    <Card title="Telemetry history">
      <div className="mb-3 grid gap-3 sm:grid-cols-3">
        <Field label="From">
          <Input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label="To">
          <Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
        <Field label="Order">
          <Select value={ordering} onChange={(e) => setOrdering(e.target.value)}>
            <option value="-recorded_at">Newest first</option>
            <option value="recorded_at">Oldest first</option>
          </Select>
        </Field>
      </div>

      {telemetry.isLoading ? (
        <Spinner />
      ) : telemetry.isError ? (
        <p className="text-sm text-red-600">Could not load telemetry.</p>
      ) : telemetry.data?.length === 0 ? (
        <EmptyState>No telemetry records for this filter.</EmptyState>
      ) : (
        <div className="max-h-96 overflow-y-auto overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-4 font-medium">Recorded</th>
                <th className="py-2 pr-4 font-medium">Position</th>
                <th className="py-2 pr-4 font-medium">Speed</th>
                <th className="py-2 pr-4 font-medium">Battery</th>
                <th className="py-2 pr-4 font-medium">Ignition</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(telemetry.data ?? []).map((record) => (
                <tr key={record.id} className="hover:bg-slate-50">
                  <td className="py-2 pr-4 text-slate-500">{dateTime(record.recorded_at)}</td>
                  <td className="py-2 pr-4">
                    <a
                      className="font-mono text-xs text-indigo-600 hover:underline"
                      href={osmLink(record.latitude, record.longitude)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {Number(record.latitude).toFixed(5)}, {Number(record.longitude).toFixed(5)}
                    </a>
                  </td>
                  <td className="py-2 pr-4">{Number(record.speed_kph).toFixed(0)} km/h</td>
                  <td className="py-2 pr-4">{orDash(record.battery_percent)}</td>
                  <td className="py-2 pr-4">
                    {record.ignition === null ? "—" : record.ignition ? "On" : "Off"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function GeofenceEditor({ vehicle }: { vehicle: Vehicle }) {
  const queryClient = useQueryClient();
  const [lat, setLat] = useState(vehicle.geofence_latitude ?? "");
  const [lng, setLng] = useState(vehicle.geofence_longitude ?? "");
  const [radius, setRadius] = useState(
    vehicle.geofence_radius_m === null || vehicle.geofence_radius_m === undefined
      ? ""
      : String(vehicle.geofence_radius_m),
  );
  const [error, setError] = useState<string | null>(null);

  const clearPayload = { geofence_latitude: null, geofence_longitude: null, geofence_radius_m: null };

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.patch<Vehicle>(`/vehicles/${vehicle.id}/`, payload).then((r) => r.data),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  const hasGeofence =
    vehicle.geofence_latitude !== null &&
    vehicle.geofence_latitude !== undefined &&
    vehicle.geofence_radius_m != null;

  function handleSave(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (lat === "" && lng === "" && radius === "") {
      mutation.mutate(clearPayload);
      return;
    }
    mutation.mutate({ geofence_latitude: lat, geofence_longitude: lng, geofence_radius_m: radius });
  }

  return (
    <Card
      title="Geofence"
      actions={
        hasGeofence ? <Badge tone="info">Radius {vehicle.geofence_radius_m} m</Badge> : undefined
      }
    >
      <form className="space-y-3" onSubmit={handleSave}>
        <FormError message={error} />
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Center latitude">
            <Input value={lat} onChange={(e) => setLat(e.target.value)} placeholder="5.6037" />
          </Field>
          <Field label="Center longitude">
            <Input value={lng} onChange={(e) => setLng(e.target.value)} placeholder="-0.1870" />
          </Field>
          <Field label="Radius (m)" hint="50–100,000 m">
            <Input value={radius} onChange={(e) => setRadius(e.target.value)} placeholder="500" />
          </Field>
        </div>
        <div className="flex gap-2">
          <Button type="submit" loading={mutation.isPending}>
            Save geofence
          </Button>
          {hasGeofence && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => mutation.mutate(clearPayload)}
            >
              Clear
            </Button>
          )}
        </div>
        <p className="text-xs text-slate-500">
          Set or clear latitude, longitude and radius together — the API rejects partial geofences.
        </p>
      </form>
    </Card>
  );
}

export function VehicleDetailPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const isStaff = canManage(user);
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);

  const vehicle = useQuery({
    queryKey: ["vehicles", id],
    queryFn: () => api.get<Vehicle>(`/vehicles/${id}/`).then((r) => r.data),
  });

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
    enabled: isStaff,
  });

  const patchVehicle = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.patch<Vehicle>(`/vehicles/${id}/`, payload).then((r) => r.data),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    },
    onError: (err) => setActionError(apiErrorMessage(err)),
  });

  if (vehicle.isLoading) return <Spinner className="mt-8" />;
  if (vehicle.isError) {
    return (
      <>
        <PageHeader title="Vehicle" />
        <Card>
          <p className="text-sm text-red-600">
            Could not load this vehicle. It may not exist or you lack access.
          </p>
        </Card>
      </>
    );
  }

  const data = vehicle.data!;
  const assignedCustomer = data.customer
    ? (customers.data ?? []).find((c) => c.id === data.customer)
    : undefined;

  return (
    <>
      <PageHeader
        title={data.registration_number}
        subtitle={`${data.make} ${data.model_name} · ${data.year} · VIN ${data.vin}`}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Status"
          actions={
            <Link to="/vehicles" className="text-xs font-semibold text-indigo-600 hover:underline">
              ← All vehicles
            </Link>
          }
        >
          <div className="mb-3 flex flex-wrap gap-2">
            <Badge tone={vehicleTone(data.status)}>{data.status}</Badge>
            <Badge tone={connectivityTone(data.connectivity_status)}>{data.connectivity_status}</Badge>
            <Badge tone={movementTone(data.movement_status)}>{data.movement_status}</Badge>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Customer</dt>
              <dd className="mt-0.5">
                {assignedCustomer ? (
                  <Link
                    to={`/customers/${assignedCustomer.id}`}
                    className="text-indigo-600 hover:underline"
                  >
                    {assignedCustomer.full_name}
                  </Link>
                ) : (
                  "Unassigned"
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Device</dt>
              <dd className="mt-0.5 font-mono text-xs">
                {data.device?.device_id
                  ? `${data.device.device_id}${data.device.enabled ? "" : " (disabled)"}`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Last position</dt>
              <dd className="mt-0.5">
                {data.last_latitude && data.last_longitude ? (
                  <a
                    className="font-mono text-xs text-indigo-600 hover:underline"
                    href={osmLink(data.last_latitude, data.last_longitude)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {Number(data.last_latitude).toFixed(5)},{" "}
                    {Number(data.last_longitude).toFixed(5)}
                  </a>
                ) : (
                  "—"
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Last report</dt>
              <dd className="mt-0.5">{dateTime(data.last_telemetry_at)}</dd>
            </div>
          </dl>

          {isStaff && (
            <form
              className="mt-4 space-y-3 border-t border-slate-100 pt-4"
              onSubmit={(event) => {
                event.preventDefault();
                const fd = new FormData(event.currentTarget);
                const customer = String(fd.get("customer") ?? "");
                patchVehicle.mutate({
                  status: String(fd.get("status") ?? ""),
                  ...(customer ? { customer } : { customer: null }),
                });
              }}
            >
              <FormError message={actionError} />
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Status">
                  <Select name="status" defaultValue={data.status}>
                    {VEHICLE_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Customer" hint="Blocked while an open loan exists.">
                  <Select name="customer" defaultValue={data.customer ?? ""}>
                    <option value="">Unassigned</option>
                    {(customers.data ?? []).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.full_name} ({c.username})
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <Button type="submit" loading={patchVehicle.isPending}>
                Save changes
              </Button>
            </form>
          )}
        </Card>

        <div className="space-y-4">
          {isStaff && <GeofenceEditor vehicle={data} />}
          <TelemetryTable vehicleId={id} />
        </div>
      </div>
    </>
  );
}
