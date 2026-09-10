import { useState } from "react";
import { Link, useParams } from "react-router-dom";
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

/** Staff dialog: change lifecycle status and (re)assign the customer. */
function VehicleEditDialog({
  open,
  onClose,
  vehicle,
}: {
  open: boolean;
  onClose: () => void;
  vehicle: Vehicle;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
    enabled: open,
  });

  const patchVehicle = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.patch<Vehicle>(`/vehicles/${vehicle.id}/`, payload).then((r) => r.data),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
      onClose();
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fd = new FormData(event.currentTarget);
    const customer = String(fd.get("customer") ?? "");
    patchVehicle.mutate({
      status: String(fd.get("status") ?? ""),
      ...(customer ? { customer } : { customer: null }),
    });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Edit vehicle"
      description={`${vehicle.registration_number} — assignment is blocked while an open loan exists.`}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />
        <Field label="Status">
          <Select name="status" defaultValue={vehicle.status}>
            {VEHICLE_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Customer">
          <Select name="customer" defaultValue={vehicle.customer ?? ""}>
            <option value="">Unassigned</option>
            {(customers.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.full_name} ({c.username})
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex gap-2">
          <Button type="submit" loading={patchVehicle.isPending} className="flex-1">
            Save changes
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/** Staff dialog: set or clear the geofence as one unit. */
function GeofenceDialog({
  open,
  onClose,
  vehicle,
}: {
  open: boolean;
  onClose: () => void;
  vehicle: Vehicle;
}) {
  const queryClient = useQueryClient();
  const [lat, setLat] = useState(vehicle.geofence_latitude ?? "");
  const [lng, setLng] = useState(vehicle.geofence_longitude ?? "");
  const [radius, setRadius] = useState(
    vehicle.geofence_radius_m === null || vehicle.geofence_radius_m === undefined
      ? ""
      : String(vehicle.geofence_radius_m),
  );
  const [error, setError] = useState<string | null>(null);

  const clearPayload = {
    geofence_latitude: null,
    geofence_longitude: null,
    geofence_radius_m: null,
  };

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.patch<Vehicle>(`/vehicles/${vehicle.id}/`, payload).then((r) => r.data),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
      onClose();
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
    <Dialog
      open={open}
      onClose={onClose}
      title="Geofence"
      description={`${vehicle.registration_number} — set or clear all three values together.`}
    >
      <form onSubmit={handleSave} className="space-y-4">
        <FormError message={error} />
        <div className="grid gap-4 sm:grid-cols-3">
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
          <Button type="submit" loading={mutation.isPending} className="flex-1">
            Save geofence
          </Button>
          {hasGeofence && (
            <Button type="button" variant="secondary" onClick={() => mutation.mutate(clearPayload)}>
              Clear geofence
            </Button>
          )}
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function VehicleDetailPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const isStaff = canManage(user);
  const [showEdit, setShowEdit] = useState(false);
  const [showGeofence, setShowGeofence] = useState(false);

  const vehicle = useQuery({
    queryKey: ["vehicles", id],
    queryFn: () => api.get<Vehicle>(`/vehicles/${id}/`).then((r) => r.data),
  });

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
    enabled: isStaff,
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
        actions={
          isStaff && (
            <>
              <Button variant="secondary" onClick={() => setShowEdit(true)}>
                Edit
              </Button>
              <Button variant="secondary" onClick={() => setShowGeofence(true)}>
                Geofence
              </Button>
            </>
          )
        }
      />

      {isStaff && data && (
        <>
          <VehicleEditDialog open={showEdit} onClose={() => setShowEdit(false)} vehicle={data} />
          <GeofenceDialog
            open={showGeofence}
            onClose={() => setShowGeofence(false)}
            vehicle={data}
          />
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Status">
          <div className="mb-3 flex flex-wrap gap-2">
            <Badge tone={vehicleTone(data.status)}>{data.status}</Badge>
            <Badge tone={connectivityTone(data.connectivity_status)}>
              {data.connectivity_status}
            </Badge>
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
            <div className="col-span-2">
              <dt className="text-xs uppercase tracking-wide text-slate-500">Geofence</dt>
              <dd className="mt-0.5 text-sm text-slate-700">
                {data.geofence_latitude != null && data.geofence_radius_m != null
                  ? `${Number(data.geofence_latitude).toFixed(5)}, ${Number(
                      data.geofence_longitude ?? "",
                    ).toFixed(5)} · radius ${data.geofence_radius_m} m`
                  : "Not set"}
              </dd>
            </div>
          </dl>
        </Card>

        <TelemetryTable vehicleId={id} />
      </div>
    </>
  );
}
