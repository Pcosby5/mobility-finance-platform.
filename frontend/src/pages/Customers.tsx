import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Badge, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { listAll } from "@/lib/api";
import { date, money } from "@/lib/format";
import type { CustomerProfile } from "@/types/api";

export function CustomersPage() {
  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: () => listAll<CustomerProfile>("/customers/"),
  });

  return (
    <>
      <PageHeader
        title="Customers"
        subtitle="Self-reported financial profiles used for demo credit screening."
      />
      <Card>
        {customers.isLoading ? (
          <Spinner />
        ) : customers.isError ? (
          <p className="text-sm text-red-600">Could not load customers.</p>
        ) : customers.data?.length === 0 ? (
          <EmptyState>No customer profiles yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-4 font-medium">Customer</th>
                  <th className="py-2 pr-4 font-medium">Employment</th>
                  <th className="py-2 pr-4 font-medium">Monthly income</th>
                  <th className="py-2 pr-4 font-medium">Existing debt</th>
                  <th className="py-2 pr-4 font-medium">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(customers.data ?? []).map((customer) => (
                  <tr key={customer.id} className="hover:bg-slate-50">
                    <td className="py-2.5 pr-4">
                      <Link
                        to={`/customers/${customer.id}`}
                        className="font-medium text-indigo-600 hover:underline"
                      >
                        {customer.full_name}
                      </Link>
                      <span className="block text-xs text-slate-500">
                        {customer.username} · {customer.phone}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4">
                      <Badge tone="neutral">{customer.employment_status}</Badge>
                    </td>
                    <td className="py-2.5 pr-4">
                      {money(customer.monthly_income, customer.currency)}
                    </td>
                    <td className="py-2.5 pr-4">{money(customer.existing_debt)}</td>
                    <td className="py-2.5 pr-4 text-slate-500">{date(customer.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
