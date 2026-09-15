export function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

export function formatMrp(mrp: number | null | undefined): string {
  if (mrp == null || Number.isNaN(Number(mrp))) return "—";
  return `₹${Number(mrp)}`;
}
