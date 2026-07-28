import { afterEach, describe, expect, it, vi } from "vitest";

// provenance-verify.ts imports ONLY `getIdToken` from lib/auth — see the
// identical note in api.auth.test.ts for why a mock of just that export is
// complete here.
const mocks = vi.hoisted(() => ({ getIdToken: vi.fn() }));
vi.mock("./auth", () => ({ getIdToken: mocks.getIdToken }));

import { fetchReelReceipt, verifyReelProvenance } from "./provenance-verify";

/** A plain 404: both functions under test short-circuit to their
 *  "unavailable" state on a non-ok response without reading the body, so
 *  this is enough to exercise the header-building logic without needing a
 *  real (golden-hash) manifest or receipt fixture. */
function notFoundResponse(): Response {
  return { ok: false, status: 404 } as Response;
}

afterEach(() => {
  mocks.getIdToken.mockReset();
});

describe("verifyReelProvenance — Authorization header", () => {
  it("guest: sends exactly { Accept: 'application/json' }, no Authorization key", async () => {
    mocks.getIdToken.mockResolvedValue(null);
    const fetchImpl = vi.fn().mockResolvedValue(notFoundResponse());
    await verifyReelProvenance("r", null, fetchImpl);
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({ Accept: "application/json" });
  });

  it("signed in: adds a fresh Authorization header alongside Accept", async () => {
    mocks.getIdToken.mockResolvedValue("verify-token");
    const fetchImpl = vi.fn().mockResolvedValue(notFoundResponse());
    await verifyReelProvenance("r", null, fetchImpl);
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({
      Accept: "application/json",
      Authorization: "Bearer verify-token",
    });
  });
});

describe("fetchReelReceipt — Authorization header", () => {
  it("guest: sends exactly { Accept: 'application/json' }", async () => {
    mocks.getIdToken.mockResolvedValue(null);
    const fetchImpl = vi.fn().mockResolvedValue(notFoundResponse());
    await fetchReelReceipt("r", fetchImpl);
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({ Accept: "application/json" });
  });

  it("signed in: adds a fresh Authorization header alongside Accept", async () => {
    mocks.getIdToken.mockResolvedValue("receipt-token");
    const fetchImpl = vi.fn().mockResolvedValue(notFoundResponse());
    await fetchReelReceipt("r", fetchImpl);
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({
      Accept: "application/json",
      Authorization: "Bearer receipt-token",
    });
  });
});
