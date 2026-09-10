import { Route, Routes } from "react-router-dom";

import { RequireAuth } from "@/auth/RequireAuth";
import { AppShell } from "@/components/AppShell";
import { AlertsPage } from "@/pages/Alerts";
import { CustomerDetailPage } from "@/pages/CustomerDetail";
import { CustomersPage } from "@/pages/Customers";
import { DashboardPage } from "@/pages/Dashboard";
import { LoanDetailPage } from "@/pages/LoanDetail";
import { LoansPage } from "@/pages/Loans";
import { LoginPage } from "@/pages/Login";
import { PaymentsPage } from "@/pages/Payments";
import { VehicleDetailPage } from "@/pages/VehicleDetail";
import { VehiclesPage } from "@/pages/Vehicles";

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
          <Route path="/payments" element={<PaymentsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
        </Route>
      </Route>

      <Route path="*" element={<LoginPage />} />
    </Routes>
  );
}
