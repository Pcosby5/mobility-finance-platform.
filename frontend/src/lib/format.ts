import type {
  ConnectivityStatus,
  LoanStatus,
  MovementStatus,
  PaymentStatus,
  RiskBand,
  VehicleStatus,
} from "@/types/api";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function money(amount: string | number | null | undefined, currency?: string): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const n = typeof amount === "string" ? Number(amount) : amount;
  if (Number.isNaN(n)) return String(amount);
  return new Intl.NumberFormat("en-US", {
    style: currency ? "currency" : "decimal",
    currency,
    maximumFractionDigits: 2,
  }).format(n);
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function date(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "never";
  const d = new Date(value).getTime();
  if (Number.isNaN(d)) return value;
  const diff = Date.now() - d;
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** Visual tone buckets for status pills. */
export type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const LOAN_TONES: Record<LoanStatus, Tone> = {
  PENDING: "warning",
  ACTIVE: "info",
  COMPLETED: "success",
  DEFAULTED: "danger",
  CANCELLED: "neutral",
};

const PAYMENT_TONES: Record<PaymentStatus, Tone> = {
  PENDING: "warning",
  SUCCESS: "success",
  FAILED: "danger",
  CANCELLED: "neutral",
};

const SEVERITY_TONES: Record<RiskBand, Tone> = {
  LOW: "success",
  MEDIUM: "warning",
  HIGH: "danger",
};

export function loanTone(status: LoanStatus): Tone {
  return LOAN_TONES[status] ?? "neutral";
}

export function paymentTone(status: PaymentStatus): Tone {
  return PAYMENT_TONES[status] ?? "neutral";
}

export function severityTone(severity: RiskBand): Tone {
  return SEVERITY_TONES[severity] ?? "neutral";
}

const VEHICLE_TONES: Record<VehicleStatus, Tone> = {
  ACTIVE: "success",
  MAINTENANCE: "warning",
  RETIRED: "neutral",
};

const CONNECTIVITY_TONES: Record<ConnectivityStatus, Tone> = {
  ONLINE: "success",
  OFFLINE: "danger",
  UNKNOWN: "neutral",
};

const MOVEMENT_TONES: Record<MovementStatus, Tone> = {
  MOVING: "info",
  PARKED: "neutral",
  UNKNOWN: "neutral",
};

export function vehicleTone(status: VehicleStatus): Tone {
  return VEHICLE_TONES[status] ?? "neutral";
}

export function connectivityTone(status: ConnectivityStatus): Tone {
  return CONNECTIVITY_TONES[status] ?? "neutral";
}

export function movementTone(status: MovementStatus): Tone {
  return MOVEMENT_TONES[status] ?? "neutral";
}

/** "—" for null/undefined/empty display values. */
export function orDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

/** Deep link to the position on OpenStreetMap (no map dependency needed). */
export function osmLink(lat: string | number, lng: string | number): string {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`;
}
