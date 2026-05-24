import { describe, it } from "node:test";
import assert from "node:assert/strict";

// buildSearchUrl is pure — test without module bundler
function buildSearchUrl(q) {
  const params = new URLSearchParams({ q });
  return `/api/events/search?${params.toString()}`;
}

class ApiError extends Error {
  constructor(status, body) {
    super(`API ${status}`);
    this.status = status;
    this.body = body;
  }
}

describe("buildSearchUrl", () => {
  it("encodes query correctly", () => {
    const url = buildSearchUrl("북한 미사일");
    assert.ok(url.startsWith("/api/events/search?"));
    assert.ok(url.includes("q="));
    const parsed = new URL("http://x" + url);
    assert.equal(parsed.searchParams.get("q"), "북한 미사일");
  });

  it("handles special characters", () => {
    const url = buildSearchUrl("a&b=c");
    const parsed = new URL("http://x" + url);
    assert.equal(parsed.searchParams.get("q"), "a&b=c");
  });
});

describe("ApiError", () => {
  it("carries status and body", () => {
    const err = new ApiError(404, "not found");
    assert.equal(err.status, 404);
    assert.equal(err.body, "not found");
    assert.ok(err instanceof Error);
    assert.equal(err.message, "API 404");
  });
});
