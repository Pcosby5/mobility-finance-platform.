import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { canManage, useAuth } from "@/auth/AuthContext";
import { cx } from "@/lib/format";
import { useTheme } from "@/theme/useTheme";

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
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const nav = canManage(user) ? STAFF_NAV : CUSTOMER_NAV;

  return (
    <div className="min-h-svh overflow-hidden bg-[radial-gradient(circle_at_top_left,var(--page-glow)_0,var(--page-bg)_32rem)]">
      <header className="sticky top-0 z-10 border-b border-[color:var(--shell-border)] bg-[color:var(--shell-bg)] shadow-sm shadow-slate-950/[0.03] backdrop-blur-2xl">
        <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:gap-5 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-7">
            <NavLink to="/dashboard" className="group flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-2xl bg-[color:var(--brand-block)] text-sm font-semibold text-[color:var(--brand-text)] shadow-lg shadow-slate-950/15">
                MF
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold tracking-tight text-[color:var(--text-strong)]">
                  Mobility Finance
                </span>
                <span className="hidden text-xs text-[color:var(--text-muted)] md:block">
                  Credit, fleet and payments
                </span>
              </span>
            </NavLink>
            <nav className="hidden items-center gap-1 rounded-full bg-[color:var(--nav-bg)] p-1 ring-1 ring-[color:var(--shell-border)] lg:flex">
              {nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    cx(
                      "rounded-full px-3.5 py-2 text-sm font-semibold transition duration-200",
                      isActive
                        ? "bg-[color:var(--nav-active)] text-[color:var(--text-strong)] shadow-sm ring-1 ring-slate-950/[0.04]"
                        : "text-[color:var(--text-muted)] hover:text-[color:var(--text-strong)]",
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            {user && (
              <span className="hidden items-center gap-3 rounded-full bg-[color:var(--nav-active)] py-1.5 pl-1.5 pr-3 ring-1 ring-[color:var(--line-soft)] md:flex">
                <span className="grid size-8 place-items-center rounded-full bg-[color:var(--nav-bg)] text-xs font-semibold text-[color:var(--text-muted)]">
                  {userInitial(user.first_name || user.username)}
                </span>
                <span className="text-right text-xs leading-tight">
                  <span className="block font-semibold text-[color:var(--text-strong)]">
                    {user.first_name || user.username}
                  </span>
                  <span className="block text-[color:var(--text-muted)]">{user.role}</span>
                </span>
              </span>
            )}
            <button
              type="button"
              onClick={toggleTheme}
              className="grid size-10 place-items-center rounded-full bg-[color:var(--nav-active)] text-[color:var(--text-strong)] shadow-sm ring-1 ring-[color:var(--line-soft)] transition hover:scale-[1.02]"
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
              title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            >
              {theme === "light" ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-4" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.8 6.8 0 0 0 9.8 9.8Z" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-4" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.4-6.4L17 7M7 17l-1.4 1.4m12.8 0L17 17M7 7 5.6 5.6" />
                  <circle cx="12" cy="12" r="4" />
                </svg>
              )}
            </button>
            <button
              onClick={handleLogout}
              className="btn-primary rounded-full px-3.5 py-2.5 text-sm font-semibold shadow-sm transition hover:opacity-90 sm:px-4"
            >
              <span className="hidden sm:inline">Sign out</span>
              <span className="sm:hidden">Exit</span>
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
                    ? "bg-[color:var(--brand-block)] text-[color:var(--brand-text)] shadow-sm"
                    : "bg-[color:var(--nav-active)] text-[color:var(--text-muted)] ring-1 ring-[color:var(--line-soft)] hover:text-[color:var(--text-strong)]",
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
