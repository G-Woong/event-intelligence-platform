"use client";

import { useState } from "react";

interface ActionResult {
  success: boolean;
  message: string;
}

async function callProxy(path: string, body?: object): Promise<ActionResult> {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { success: false, message: `Error ${res.status}: ${JSON.stringify(data)}` };
    }
    return { success: true, message: JSON.stringify(data, null, 2) };
  } catch (err) {
    return { success: false, message: String(err) };
  }
}

function ActionButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded-md bg-gray-700 px-4 py-2 text-sm text-white hover:bg-gray-600 disabled:opacity-50 transition-colors"
    >
      {label}
    </button>
  );
}

export default function AdminPanel() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ActionResult | null>(null);

  async function run(path: string, body?: object) {
    setLoading(true);
    setResult(null);
    const r = await callProxy(path, body);
    setResult(r);
    setLoading(false);
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-yellow-800 bg-yellow-950/20 px-4 py-3 text-sm text-yellow-300">
        ADMIN_API_TOKEN이 비어있으면 모든 admin 동작이 인증 없이 실행됩니다 (dev 전용).
      </div>

      <div className="flex flex-wrap gap-3">
        <ActionButton
          label="Reindex (dry-run)"
          disabled={loading}
          onClick={() => run("/api/admin/reindex", { dry_run: true, limit: 1000 })}
        />
        <ActionButton
          label="Reindex (실행)"
          disabled={loading}
          onClick={() => run("/api/admin/reindex", { dry_run: false, limit: 1000 })}
        />
        <ActionButton
          label="Reconcile (dry-run)"
          disabled={loading}
          onClick={() => run("/api/admin/reconcile", { dry_run: true })}
        />
        <ActionButton
          label="Reconcile (실행)"
          disabled={loading}
          onClick={() => run("/api/admin/reconcile", { dry_run: false })}
        />
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <div className="h-4 w-4 animate-spin rounded-full border border-gray-600 border-t-blue-400" />
          실행 중...
        </div>
      )}

      {result && (
        <div
          className={`rounded-lg border p-4 ${
            result.success
              ? "border-green-800 bg-green-950/20 text-green-300"
              : "border-red-800 bg-red-950/20 text-red-300"
          }`}
        >
          <pre className="whitespace-pre-wrap text-xs">{result.message}</pre>
        </div>
      )}
    </div>
  );
}
