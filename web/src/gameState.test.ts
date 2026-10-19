import { describe, expect, it } from "vitest";
import { applyEvent, parseEvent, positionAt, START_FEN, type Game } from "./gameState";

const base: Game = {
  id: "g1",
  event: "Test",
  white: "Ann",
  black: "Bo",
  result: "*",
  start_fen: null,
  ply: 1,
  fen: "after-e4",
  created_at: "2026-10-19T00:00:00Z",
  updated_at: "2026-10-19T00:00:00Z",
  moves: [{ ply: 1, san: "e4", uci: "e2e4", fen: "after-e4" }],
};

describe("applyEvent", () => {
  it("replaces state on snapshot", () => {
    expect(applyEvent(null, { type: "snapshot", game: base })).toBe(base);
    const empty = { ...base, moves: [], ply: 0 };
    expect(applyEvent(base, { type: "snapshot", game: empty })).toBe(empty);
  });

  it("appends the next move and updates fen and result", () => {
    const next = applyEvent(base, {
      type: "move",
      ply: 2,
      san: "e5",
      uci: "e7e5",
      fen: "after-e5",
      result: "*",
    });
    expect(next?.moves.map((m) => m.san)).toEqual(["e4", "e5"]);
    expect(next?.fen).toBe("after-e5");
    expect(next?.ply).toBe(2);
  });

  it("ignores duplicates, gaps and moves before any snapshot", () => {
    const dup = { type: "move", ply: 1, san: "e4", uci: "e2e4", fen: "x", result: "*" } as const;
    expect(applyEvent(base, dup)).toBe(base);
    expect(applyEvent(base, { ...dup, ply: 5 })).toBe(base);
    expect(applyEvent(null, { ...dup, ply: 1 })).toBeNull();
  });
});

describe("positionAt", () => {
  const two: Game = {
    ...base,
    ply: 2,
    fen: "after-e5",
    moves: [...base.moves, { ply: 2, san: "e5", uci: "e7e5", fen: "after-e5" }],
  };

  it("follows the live position when viewPly is null or past the end", () => {
    expect(positionAt(two, null)).toEqual({ fen: "after-e5", lastMove: "e7e5" });
    expect(positionAt(two, 9)).toEqual({ fen: "after-e5", lastMove: "e7e5" });
  });

  it("shows earlier plies and the starting position", () => {
    expect(positionAt(two, 1)).toEqual({ fen: "after-e4", lastMove: "e2e4" });
    expect(positionAt(two, 0).fen).toBe(START_FEN);
    expect(positionAt({ ...two, start_fen: "custom" }, 0).fen).toBe("custom");
  });
});

describe("parseEvent", () => {
  it("accepts known events and rejects junk", () => {
    expect(parseEvent(JSON.stringify({ type: "snapshot", game: base }))?.type).toBe("snapshot");
    expect(parseEvent("not json")).toBeNull();
    expect(parseEvent(JSON.stringify({ type: "other" }))).toBeNull();
    expect(parseEvent(JSON.stringify(5))).toBeNull();
    expect(parseEvent(new ArrayBuffer(1))).toBeNull();
  });
});
