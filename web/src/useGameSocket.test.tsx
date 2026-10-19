import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Game } from "./gameState";
import { backoffMs, useGameSocket } from "./useGameSocket";

class FakeSocket {
  static instances: FakeSocket[] = [];
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  receive(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
  drop(code = 1006) {
    this.onclose?.({ code } as CloseEvent);
  }
}

const game: Game = {
  id: "g1",
  event: "Test",
  white: "Ann",
  black: "Bo",
  result: "*",
  start_fen: null,
  ply: 0,
  fen: "start",
  created_at: "",
  updated_at: "",
  moves: [],
};

beforeEach(() => {
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200 }));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("backoffMs", () => {
  it("doubles from one second and caps at ten", () => {
    expect([0, 1, 2, 3, 4, 10].map(backoffMs)).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });
});

describe("useGameSocket", () => {
  it("goes live on a snapshot and applies later moves", () => {
    const { result } = renderHook(() => useGameSocket("g1"));
    expect(result.current.status).toBe("connecting");
    const sock = FakeSocket.instances[0]!;
    expect(sock.url).toContain("/ws/games/g1");
    act(() => sock.receive({ type: "snapshot", game }));
    expect(result.current.status).toBe("live");
    act(() =>
      sock.receive({ type: "move", ply: 1, san: "e4", uci: "e2e4", fen: "f1", result: "*" }),
    );
    expect(result.current.game?.moves).toHaveLength(1);
  });

  it("reconnects with backoff after a drop and keeps showing the game", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useGameSocket("g1"));
    act(() => FakeSocket.instances[0]!.receive({ type: "snapshot", game }));
    await act(async () => FakeSocket.instances[0]!.drop());
    expect(result.current.status).toBe("reconnecting");
    expect(result.current.game).not.toBeNull();
    expect(FakeSocket.instances).toHaveLength(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(FakeSocket.instances).toHaveLength(2);
    act(() => FakeSocket.instances[1]!.receive({ type: "snapshot", game: { ...game, fen: "resynced" } }));
    expect(result.current.status).toBe("live");
    expect(result.current.game?.fen).toBe("resynced");
  });

  it("reports an unknown game instead of retrying forever", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 404 }));
    const { result } = renderHook(() => useGameSocket("nope"));
    await act(async () => FakeSocket.instances[0]!.drop());
    await waitFor(() => expect(result.current.status).toBe("notfound"));
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("closes the socket on unmount and does not reconnect", async () => {
    const { unmount } = renderHook(() => useGameSocket("g1"));
    const sock = FakeSocket.instances[0]!;
    unmount();
    expect(sock.closed).toBe(true);
    await act(async () => sock.drop());
    expect(FakeSocket.instances).toHaveLength(1);
  });
});
