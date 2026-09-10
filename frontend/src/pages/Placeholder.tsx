import { Card, PageHeader } from "@/components/ui";

export function PlaceholderPage({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <Card>
        <p className="text-sm text-slate-500">
          This section is next up — its API endpoints are already wired in the shared client.
        </p>
      </Card>
    </>
  );
}
