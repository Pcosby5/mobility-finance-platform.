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

function userInitial(name: string | undefined): string {
  return (name?.trim().charAt(0) || "M").toUpperCase();
}

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const nav = canManage(user) ? STAFF_NAV : CUSTOMER_NAV;

  return (
    <div className="min-h-svh overflow-hidden bg-[radial-gradient(circle_at_top_left,#eef2ff_0,#f6f7f9_32rem)]">
      <header className="sticky top-0 z-10 border-b border-white/70 bg-white/76 shadow-sm shadow-slate-950/[0.03] backdrop-blur-2xl">
        <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-5 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-7">
            <NavLink to="/dashboard" className="group flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-2xl bg-slate-950 text-sm font-semibold text-white shadow-lg shadow-slate-950/15">
                MF
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold tracking-tight text-slate-950">
                  Mobility Finance
                </span>
                <span className="hidden text-xs text-slate-500 sm:block">
                  Credit, fleet and payments
                </span>
              </span>
            </NavLink>
            <nav className="hidden items-center gap-1 rounded-full bg-slate-100/80 p-1 ring-1 ring-white/80 lg:flex">
              {nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cx(
                      "rounded-full px-3.5 py-2 text-sm font-semibold transition duration-200",
                      isActive
                        ? "bg-white text-slate-950 shadow-sm ring-1 ring-slate-950/[0.04]"
                        : "text-slate-500 hover:text-slate-950",
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
              <span className="hidden items-center gap-3 rounded-full bg-white/80 py-1.5 pl-1.5 pr-3 ring-1 ring-slate-200 sm:flex">
                <span className="grid size-8 place-items-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">
                  {userInitial(user.first_name || user.username)}
                </span>
                <span className="text-right text-xs leading-tight">
                  <span className="block font-semibold text-slate-950">
                    {user.first_name || user.username}
                  </span>
                  <span className="block text-slate-500">{user.role}</span>
                </span>
              </span>
            )}
            <button
              onClick={handleLogout}
              className="rounded-full bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"
            >
              Sign out
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-3 sm:px-6 lg:hidden lg:px-8">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cx(
                  "shrink-0 rounded-full px-3.5 py-2 text-sm font-semibold transition",
                  isActive
                    ? "bg-slate-950 text-white shadow-sm"
                    : "bg-white/70 text-slate-600 ring-1 ring-slate-200 hover:text-slate-950",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
}
