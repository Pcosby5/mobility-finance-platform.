import { Route, Routes } from "react-router-dom";

import { RequireAuth } from "@/auth/RequireAuth";
import { AppShell } from "@/components/AppShell";
import { CustomerDetailPage } from "@/pages/CustomerDetail";
import { CustomersPage } from "@/pages/Customers";
import { DashboardPage } from "@/pages/Dashboard";
import { LoanDetailPage } from "@/pages/LoanDetail";
import { LoansPage } from "@/pages/Loans";
import { LoginPage } from "@/pages/Login";
import { VehicleDetailPage } from "@/pages/VehicleDetail";
import { VehiclesPage } from "@/pages/Vehicles";
import { PlaceholderPage } from "@/pages/Placeholder";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/customers" element={<CustomersPage />} />
          <Route path="/customers/:id" element={<CustomerDetailPage />} />
          <Route path="/vehicles" element={<VehiclesPage />} />
          <Route path="/vehicles/:id" element={<VehicleDetailPage />} />
          <Route path="/loans" element={<LoansPage />} />
          <Route path="/loans/:id" element={<LoanDetailPage />} />
          <Route
            path="/payments"
            element={
              <PlaceholderPage
                title="Payments"
                subtitle="Initialization, verification and webhook events."
              />
            }
          />
          <Route
            path="/alerts"
            element={
              <PlaceholderPage title="Alerts" subtitle="Geofence, speeding and offline events." />
            }
          />
        </Route>
      </Route>

      <Route path="*" element={<LoginPage />} />
    </Routes>
  );
}
