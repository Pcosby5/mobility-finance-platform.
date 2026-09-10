import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { canManage, useAuth } from "@/auth/AuthContext";
import { cx } from "@/lib/format";

const STAFF_NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/customers", label: "Customers" },
  { to: "/vehicles", label: "Vehicles" },
  { to: "/loans", label: "Loans" },
  { to: "/payments", label: "Payments" },
  { to: "/alerts", label: "Alerts" },
] as const;

const CUSTOMER_NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/vehicles", label: "Vehicles" },
  { to: "/loans", label: "Loans" },
  { to: "/alerts", label: "Alerts" },
] as const;

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const nav = canManage(user) ? STAFF_NAV : CUSTOMER_NAV;

  return (
    <div className="min-h-svh">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4">
          <div className="flex items-center gap-6">
            <NavLink to="/dashboard" className="text-sm font-bold tracking-tight text-indigo-600">
              Mobility Finance
            </NavLink>
            <nav className="hidden items-center gap-1 md:flex">
              {nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cx(
                      "rounded-md px-3 py-1.5 text-sm font-medium transition",
                      isActive
                        ? "bg-indigo-50 text-indigo-700"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {user && (
              <span className="hidden text-right text-xs leading-tight sm:block">
                <span className="block font-semibold text-slate-900">
                  {user.first_name || user.username}
                </span>
                <span className="block text-slate-500">{user.role}</span>
              </span>
            )}
            <button
              onClick={handleLogout}
              className="rounded-md bg-white px-3 py-2 text-sm font-semibold text-slate-900 shadow-sm ring-1 ring-inset ring-slate-300 transition hover:bg-slate-50"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
