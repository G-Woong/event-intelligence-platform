import type { HealthResponse } from "@/lib/api/types";

function StatusDot({ status }: { status: string }) {
  const isOk = status === "ok" || status === "healthy" || status === "connected";
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${isOk ? "bg-green-400" : "bg-red-400"}`}
    />
  );
}

export default function HealthStatus({ health }: { health: HealthResponse }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="mb-3 flex items-center gap-2">
        <StatusDot status={health.status} />
        <span className="font-semibold text-white">
          Backend {health.status}
        </span>
        {health.version && (
          <span className="ml-auto text-xs text-gray-500">v{health.version}</span>
        )}
      </div>
      {health.components && (
        <dl className="grid grid-cols-2 gap-2">
          {Object.entries(health.components).map(([name, status]) => (
            <div key={name} className="flex items-center gap-2">
              <StatusDot status={status} />
              <dt className="text-xs text-gray-400 capitalize">{name}</dt>
              <dd className="ml-auto text-xs text-gray-500">{status}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
