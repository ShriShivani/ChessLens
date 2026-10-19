import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseRoute } from "../App";
import type { GameSummary, MoveRow } from "../gameState";
import GameList from "./GameList";
import MoveList from "./MoveList";

const moves: MoveRow[] = [
  { ply: 1, san: "e4", uci: "e2e4", fen: "a" },
  { ply: 2, san: "e5", uci: "e7e5", fen: "b" },
  { ply: 3, san: "Nf3", uci: "g1f3", fen: "c" },
];

afterEach(() => vi.unstubAllGlobals());

describe("MoveList", () => {
  it("shows an empty state", () => {
    render(<MoveList moves={[]} current={0} onSelect={() => {}} />);
    expect(screen.getByText("No moves yet.")).toBeInTheDocument();
  });

  it("pairs moves, marks the current one and reports clicks", async () => {
    const onSelect = vi.fn();
    render(<MoveList moves={moves} current={2} onSelect={onSelect} />);
    expect(screen.getByText("1.")).toBeInTheDocument();
    expect(screen.getByText("2.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "e5" })).toHaveAttribute("aria-current", "true");
    await userEvent.click(screen.getByRole("button", { name: "Nf3" }));
    expect(onSelect).toHaveBeenCalledWith(3);
  });
});

describe("GameList", () => {
  const summary: GameSummary = {
    id: "abc",
    event: "Club night",
    white: "Ann",
    black: "Bo",
    result: "*",
    start_fen: null,
    ply: 1,
    fen: "",
    created_at: "",
    updated_at: "",
  };

  it("lists games with links to their pages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [summary] }),
    );
    render(<GameList />);
    const link = await screen.findByRole("link", { name: /Ann vs Bo/ });
    expect(link).toHaveAttribute("href", "#/game/abc");
    expect(link).toHaveTextContent("1 move");
    expect(link).toHaveTextContent("in progress");
  });

  it("shows an empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    render(<GameList />);
    expect(await screen.findByText("No games yet.")).toBeInTheDocument();
  });

  it("shows an error with retry when the server is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    render(<GameList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("server returned 500");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => [summary] }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("link", { name: /Ann vs Bo/ })).toBeInTheDocument());
  });
});

describe("parseRoute", () => {
  it("routes hashes to pages", () => {
    expect(parseRoute("")).toEqual({ page: "list" });
    expect(parseRoute("#/")).toEqual({ page: "list" });
    expect(parseRoute("#/game/abc123")).toEqual({ page: "game", id: "abc123" });
    expect(parseRoute("#/game/")).toEqual({ page: "list" });
  });
});
