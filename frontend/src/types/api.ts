/** Shapes returned by the Mobility Finance API (drf-spectacular schema at
 * /api/schema/ is the source of truth; codegen can replace this file later).
 * Fields the serializers may omit are optional to keep the UI defensive. */

export type Role = "ADMIN" | "CUSTOMER" | "OPERATIONS";

export interface User {
  id: string;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  role: Role;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export type EmploymentStatus = "EMPLOYED" | "SELF_EMPLOYED" | "UNEMPLOYED" | "STUDENT";
export type Currency = "GHS" | "NGN" | "USD";

export interface CustomerProfile {
  id: string;
  user: string;
  username?: string;
  full_name: string;
  phone: string;
  email?: string;
  employment_status: EmploymentStatus;
  employment_duration_months: number | null;
  currency: Currency;
  monthly_income: string;
  existing_debt: string;
  monthly_debt_repayment: string;
  created_at?: string;
  updated_at?: string;
}

export type RiskBand = "LOW" | "MEDIUM" | "HIGH";
export type Decision = "APPROVED" | "REVIEW" | "REJECTED";

export interface CreditFactor {
  code?: string;
  summary: string;
  detail?: string;
  points?: number;
}

export interface CreditAssessment {
  id: string;
  customer: string;
  score: number;
  risk_band: RiskBand;
  decision: Decision;
  factors: CreditFactor[];
  policy_version?: string;
  created_at: string;
}

export type VehicleStatus = "ACTIVE" | "MAINTENANCE" | "RETIRED";
export type ConnectivityStatus = "UNKNOWN" | "ONLINE" | "OFFLINE";
export type MovementStatus = "UNKNOWN" | "MOVING" | "PARKED";

export interface DeviceSummary {
  id?: string;
  device_id?: string;
  enabled?: boolean;
}

export interface Vehicle {
  id: string;
  registration_number: string;
  vin: string;
  make: string;
  model_name: string;
  year: number;
  customer: string | null;
  status: VehicleStatus;
  connectivity_status: ConnectivityStatus;
  movement_status: MovementStatus;
  last_latitude: string | null;
  last_longitude: string | null;
  last_telemetry_at: string | null;
  geofence_latitude?: string | null;
  geofence_longitude?: string | null;
  geofence_radius_m?: number | null;
  device?: DeviceSummary | null;
}

export interface Device {
  id: string;
  device_id: string;
  vehicle: string | null;
  enabled: boolean;
}

export type LoanStatus = "PENDING" | "ACTIVE" | "COMPLETED" | "DEFAULTED" | "CANCELLED";

export interface Loan {
  id: string;
  customer: string;
  vehicle: string;
  credit_assessment: string;
  created_by?: string | null;
  currency: Currency;
  principal_amount: string;
  annual_interest_rate: string;
  duration_months: number;
  first_repayment_date?: string | null;
  total_interest: string;
  total_repayable: string;
  monthly_repayment: string;
  final_repayment: string;
  outstanding_balance: string;
  status: LoanStatus;
  policy_version?: string;
  origination_snapshot?: Record<string, unknown>;
  activated_at?: string | null;
  cancelled_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface Installment {
  id: string;
  loan: string;
  number: number;
  due_date: string;
  principal_due: string;
  interest_due: string;
  amount_due: string;
}

export type PaymentProvider = "PAYSTACK" | "MOCK_MOMO";
export type PaymentStatus = "PENDING" | "SUCCESS" | "FAILED" | "CANCELLED";

export interface Payment {
  id: string;
  loan: string;
  reference: string;
  provider: PaymentProvider;
  currency: Currency;
  amount: string;
  status: PaymentStatus;
  provider_transaction_id?: string | null;
  failure_reason?: string;
  created_at: string;
}

export interface WebhookEvent {
  id: string;
  provider: PaymentProvider;
  event_type: string;
  delivery_reference: string;
  status: "RECEIVED" | "PROCESSED" | "IGNORED";
  note: string;
  received_at: string;
  processed_at?: string | null;
}

export interface TelemetryRecord {
  id: string;
  vehicle: string;
  recorded_at: string;
  latitude: string;
  longitude: string;
  speed_kph: string;
  heading_deg: number | null;
  battery_percent: number | null;
  ignition: boolean | null;
}

export type AlertType = "GEOFENCE_EXIT" | "SPEEDING" | "LOW_BATTERY" | "OFFLINE";

export interface Alert {
  id: string;
  vehicle: string;
  type: AlertType;
  message: string;
  severity: RiskBand;
  resolved_at: string | null;
  resolved_by?: string | null;
  created_at: string;
}

/** DRF PageNumberPagination envelope. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
