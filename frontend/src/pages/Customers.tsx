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
            <table className="data-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Employment</th>
                  <th>Monthly income</th>
                  <th>Existing debt</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {(customers.data ?? []).map((customer) => (
                  <tr key={customer.id}>
                    <td>
                      <Link
                        to={`/customers/${customer.id}`}
                        className="font-medium text-link hover:underline"
                      >
                        {customer.full_name}
                      </Link>
                      <span className="block text-xs text-[color:var(--text-muted)]">
                        {customer.username} · {customer.phone}
                      </span>
                    </td>
                    <td>
                      <Badge tone="neutral">{customer.employment_status}</Badge>
                    </td>
                    <td>
                      {money(customer.monthly_income, customer.currency)}
                    </td>
                    <td>{money(customer.existing_debt)}</td>
                    <td className="text-[color:var(--text-muted)]">{date(customer.created_at)}</td>
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
