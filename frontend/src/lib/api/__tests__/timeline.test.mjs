import { describe, it } from "node:test";
import assert from "node:assert/strict";

// buildTimelineUrl / isSafeHttpUrl 은 순수 함수 — 번들러 없이 미러링해 검증
// (client.ts / EventUpdateItem.tsx 의 동일 로직과 일치 유지; 기존 client.test.mjs 패턴).
function buildTimelineUrl(limit = 20, offset = 0) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return `/api/events/timeline?${params.toString()}`;
}

function isSafeHttpUrl(u) {
  return !!u && (u.startsWith("http://") || u.startsWith("https://"));
}

describe("buildTimelineUrl", () => {
  it("uses default pagination", () => {
    const url = buildTimelineUrl();
    const parsed = new URL("http://x" + url);
    assert.equal(parsed.pathname, "/api/events/timeline");
    assert.equal(parsed.searchParams.get("limit"), "20");
    assert.equal(parsed.searchParams.get("offset"), "0");
  });

  it("encodes explicit limit/offset", () => {
    const url = buildTimelineUrl(50, 100);
    const parsed = new URL("http://x" + url);
    assert.equal(parsed.searchParams.get("limit"), "50");
    assert.equal(parsed.searchParams.get("offset"), "100");
  });
});

describe("isSafeHttpUrl", () => {
  it("accepts http and https", () => {
    assert.ok(isSafeHttpUrl("https://example.com/a"));
    assert.ok(isSafeHttpUrl("http://example.com"));
  });

  it("rejects non-http schemes and empty", () => {
    assert.ok(!isSafeHttpUrl("javascript:alert(1)"));
    assert.ok(!isSafeHttpUrl("data:text/html,x"));
    assert.ok(!isSafeHttpUrl(""));
    assert.ok(!isSafeHttpUrl(undefined));
  });
});
