export default function StatusPill({ status }: { status: string | null }) {
  const color =
    status === "completed"
      ? "bg-emerald-500/20 text-emerald-300"
      : status === "running"
        ? "bg-amber-500/20 text-amber-300"
        : status === "failed"
          ? "bg-red-500/20 text-red-300"
          : "bg-ink-500/20 text-ink-300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {status ?? "unknown"}
    </span>
  );
}
