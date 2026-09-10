import { useState } from "react";
import { Link } from "react-router-dom";
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
import { connectivityTone, movementTone, relativeTime, vehicleTone } from "@/lib/format";
import type { CustomerProfile, Vehicle, VehicleStatus } from "@/types/api";

const VEHICLE_STATUSES: VehicleStatus[] = ["ACTIVE", "MAINTENANCE", "RETIRED"];

type VehicleForm = {
  registration_number: string;
  vin: string;
  make: string;
  model_name: string;
  year: string;
  status: VehicleStatus;
  customer: string;
};

const EMPTY_VEHICLE_FORM: VehicleForm = {
  registration_number: "",
  vin: "",
  make: "",
  model_name: "",
  year: "",
  status: "ACTIVE",
  customer: "",
};

/** Staff-only create dialog; telemetry fields are server-owned. */
function VehicleCreateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<VehicleForm>(EMPTY_VEHICLE_FORM);
  const [error, setError] = useState<string | null>(null);

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
    enabled: open,
  });

  const createVehicle = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post<Vehicle>("/vehicles/", payload).then((r) => r.data),
    onSuccess: () => {
      setError(null);
      setForm(EMPTY_VEHICLE_FORM);
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
      onClose();
    },
    onError: (err) => setError(apiErrorMessage(err)),
  });

  function update<K extends keyof VehicleForm>(key: K, value: VehicleForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const payload: Record<string, unknown> = {
      registration_number: form.registration_number.trim().toUpperCase(),
      vin: form.vin.trim().toUpperCase(),
      make: form.make.trim(),
      model_name: form.model_name.trim(),
      year: Number(form.year),
      status: form.status,
      ...(form.customer ? { customer: form.customer } : {}),
    };
    createVehicle.mutate(payload);
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="lg"
      title="Add a vehicle"
      description="Identifiers are normalized to uppercase; telemetry fields are read-only."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Registration number">
            <Input
              value={form.registration_number}
              onChange={(e) => update("registration_number", e.target.value)}
              placeholder="DEMO-001"
              required
            />
          </Field>
          <Field label="VIN">
            <Input value={form.vin} onChange={(e) => update("vin", e.target.value)} required />
          </Field>
          <Field label="Make">
            <Input value={form.make} onChange={(e) => update("make", e.target.value)} required />
          </Field>
          <Field label="Model">
            <Input
              value={form.model_name}
              onChange={(e) => update("model_name", e.target.value)}
              required
            />
          </Field>
          <Field label="Year">
            <Input
              type="number"
              min={1900}
              max={new Date().getFullYear() + 1}
              value={form.year}
              onChange={(e) => update("year", e.target.value)}
              required
            />
          </Field>
          <Field label="Status">
            <Select
              value={form.status}
              onChange={(e) => update("status", e.target.value as VehicleStatus)}
            >
              {VEHICLE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </Select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Assign to customer" hint="Optional — can be assigned later.">
              <Select value={form.customer} onChange={(e) => update("customer", e.target.value)}>
                <option value="">Unassigned</option>
                {(customers.data ?? []).map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.full_name} ({customer.username})
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </div>
        <div className="flex gap-2">
          <Button type="submit" loading={createVehicle.isPending} className="flex-1">
            Create vehicle
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function VehiclesPage() {
  const { user } = useAuth();
  const isStaff = canManage(user);
  const [showCreate, setShowCreate] = useState(false);

  const vehicles = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => listAll<Vehicle>("/vehicles/"),
  });

  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
    enabled: isStaff,
  });

  return (
    <>
      <PageHeader
        title="Vehicles"
        subtitle={
          isStaff
            ? "Inventory, assignment and live telemetry status."
            : "Your financed vehicles and their live status."
        }
        actions={
          isStaff && (
            <Button variant="secondary" onClick={() => setShowCreate(true)}>
              Add vehicle
            </Button>
          )
        }
      />

      {isStaff && <VehicleCreateDialog open={showCreate} onClose={() => setShowCreate(false)} />}

      <Card>
        {vehicles.isLoading ? (
          <Spinner />
        ) : vehicles.isError ? (
          <p className="text-sm text-red-600">Could not load vehicles.</p>
        ) : vehicles.data?.length === 0 ? (
          <EmptyState>
            {isStaff ? "No vehicles yet — add the first one." : "No vehicles assigned to you yet."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-4 font-medium">Vehicle</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium">Connectivity</th>
                  <th className="py-2 pr-4 font-medium">Movement</th>
                  <th className="py-2 pr-4 font-medium">Last seen</th>
                  {isStaff && <th className="py-2 pr-4 font-medium">Customer</th>}
                  <th className="py-2 pr-4 font-medium">Device</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(vehicles.data ?? []).map((vehicle) => {
                  const assigned = vehicle.customer
                    ? (customers.data ?? []).find((c) => c.id === vehicle.customer)
                    : undefined;
                  return (
                    <tr key={vehicle.id} className="hover:bg-slate-50">
                      <td className="py-2.5 pr-4">
                        <Link
                          to={`/vehicles/${vehicle.id}`}
                          className="font-medium text-indigo-600 hover:underline"
                        >
                          {vehicle.registration_number}
                        </Link>
                        <span className="block text-xs text-slate-500">
                          {vehicle.make} {vehicle.model_name} · {vehicle.year}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge tone={vehicleTone(vehicle.status)}>{vehicle.status}</Badge>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge tone={connectivityTone(vehicle.connectivity_status)}>
                          {vehicle.connectivity_status}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge tone={movementTone(vehicle.movement_status)}>
                          {vehicle.movement_status}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-4 text-slate-500">
                        {relativeTime(vehicle.last_telemetry_at)}
                      </td>
                      {isStaff && (
                        <td className="py-2.5 pr-4 text-slate-500">
                          {assigned ? assigned.full_name : vehicle.customer ? "—" : "Unassigned"}
                        </td>
                      )}
                      <td className="py-2.5 pr-4 text-slate-500">
                        {vehicle.device?.device_id ? (
                          vehicle.device.enabled ? (
                            <span className="font-mono text-xs">{vehicle.device.device_id}</span>
                          ) : (
                            <span className="font-mono text-xs text-slate-400">
                              {vehicle.device.device_id} (disabled)
                            </span>
                          )
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
