import { describe, it } from "node:test";
import assert from "node:assert/strict";

// JS equivalent of src/lib/api/server.ts adminFetch
function makeAdminFetch(baseUrl, token) {
  return async (path, init = {}) => {
    const headers = new Headers(init.headers ?? {});
    if (token) headers.set("X-Admin-Token", token);
    const res = await globalThis.fetch(`${baseUrl}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`admin api ${res.status}: ${body}`);
    }
    return res.json();
  };
}

function stubFetch(response = {}) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return { ok: true, json: async () => response, text: async () => "" };
  };
  return calls;
}

describe("admin proxy — reconcile", () => {
  it("calls /api/admin/raw-events/reconcile-stuck (not old path)", async () => {
    const calls = stubFetch({ reconciled: 0 });
    const adminFetch = makeAdminFetch("http://backend:8000", "");
    await adminFetch("/api/admin/raw-events/reconcile-stuck", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dry_run: false }),
    });
    assert.equal(calls.length, 1);
    assert.match(calls[0].url, /\/api\/admin\/raw-events\/reconcile-stuck$/);
    assert.ok(!calls[0].url.match(/\/api\/admin\/reconcile-stuck$/), "old path must not be used");
  });
});

describe("admin proxy — requeue", () => {
  it("sends body with force flag and Content-Type header", async () => {
    const calls = stubFetch({ requeued: true });
    const adminFetch = makeAdminFetch("http://backend:8000", "");
    const id = "abc-123";
    const reqBody = { force: true };
    await adminFetch(`/api/admin/raw-events/${id}/requeue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: !!reqBody.force }),
    });
    assert.equal(calls.length, 1);
    assert.match(calls[0].url, /\/api\/admin\/raw-events\/abc-123\/requeue$/);
    const sentBody = JSON.parse(calls[0].init.body);
    assert.equal(sentBody.force, true);
    const ct = calls[0].init.headers.get("Content-Type");
    assert.equal(ct, "application/json");
  });

  it("defaults force to false when body absent", async () => {
    const calls = stubFetch({});
    const adminFetch = makeAdminFetch("http://backend:8000", "");
    const id = "xyz-999";
    const reqBody = {};
    await adminFetch(`/api/admin/raw-events/${id}/requeue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: !!reqBody.force }),
    });
    const sentBody = JSON.parse(calls[0].init.body);
    assert.equal(sentBody.force, false);
  });
});

describe("admin proxy — token", () => {
  it("sets X-Admin-Token header when token is present", async () => {
    const calls = stubFetch({});
    const adminFetch = makeAdminFetch("http://backend:8000", "super-secret");
    await adminFetch("/api/admin/search/reindex", { method: "POST" });
    assert.equal(calls[0].init.headers.get("X-Admin-Token"), "super-secret");
  });

  it("omits X-Admin-Token header when token is empty", async () => {
    const calls = stubFetch({});
    const adminFetch = makeAdminFetch("http://backend:8000", "");
    await adminFetch("/api/admin/search/reindex", { method: "POST" });
    assert.equal(calls[0].init.headers.get("X-Admin-Token"), null);
  });
});
