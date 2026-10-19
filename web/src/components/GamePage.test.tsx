import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Game } from "../gameState";
import type { ConnectionStatus } from "../useGameSocket";
import GamePage from "./GamePage";

const hook = vi.hoisted(() => ({
  value: { game: null, status: "connecting" } as { game: Game | null; status: ConnectionStatus },
}));

vi.mock("../useGameSocket", () => ({ useGameSocket: () => hook.value }));
vi.mock("./BoardView", () => ({
  default: ({ fen, lastMove }: { fen: string; lastMove?: string }) => (
    <div data-testid="board" data-fen={fen} data-last={lastMove ?? ""} />
  ),
}));

const game: Game = {
  id: "g1",
  event: "Club night",
  white: "Ann",
  black: "Bo",
  result: "*",
  start_fen: null,
  ply: 2,
  fen: "f2",
  created_at: "",
  updated_at: "",
  moves: [
    { ply: 1, san: "e4", uci: "e2e4", fen: "f1" },
    { ply: 2, san: "e5", uci: "e7e5", fen: "f2" },
  ],
};

beforeEach(() => {
  hook.value = { game, status: "live" };
});

describe("GamePage", () => {
  it("shows connecting and not-found states", () => {
    hook.value = { game: null, status: "connecting" };
    const { unmount } = render(<GamePage gameId="g1" />);
    expect(screen.getByRole("status")).toHaveTextContent("Connecting");
    unmount();
    hook.value = { game: null, status: "notfound" };
    render(<GamePage gameId="g1" />);
    expect(screen.getByRole("alert")).toHaveTextContent("was not found");
  });

  it("follows the live position and links the PGN download", () => {
    render(<GamePage gameId="g1" />);
    expect(screen.getByTestId("board")).toHaveAttribute("data-fen", "f2");
    expect(screen.getByRole("link", { name: "Download PGN" })).toHaveAttribute(
      "href",
      "/api/games/g1/pgn",
    );
    expect(screen.getByRole("heading")).toHaveTextContent("Ann vs Bo");
  });

  it("steps back through the game with the buttons and returns to live", async () => {
    render(<GamePage gameId="g1" />);
    await userEvent.click(screen.getByRole("button", { name: "Previous move" }));
    expect(screen.getByTestId("board")).toHaveAttribute("data-fen", "f1");
    await userEvent.click(screen.getByRole("button", { name: "First move" }));
    expect(screen.getByTestId("board")).toHaveAttribute("data-last", "");
    await userEvent.click(screen.getByRole("button", { name: "Latest move" }));
    expect(screen.getByTestId("board")).toHaveAttribute("data-fen", "f2");
  });

  it("supports arrow keys and clicking a move", async () => {
    render(<GamePage gameId="g1" />);
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByTestId("board")).toHaveAttribute("data-fen", "f1");
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByTestId("board")).toHaveAttribute("data-fen", "f2");
    await userEvent.click(screen.getByRole("button", { name: "e4" }));
    expect(screen.getByTestId("board")).toHaveAttribute("data-fen", "f1");
  });

  it("displays the result and reconnecting status", () => {
    hook.value = { game: { ...game, result: "1-0" }, status: "reconnecting" };
    render(<GamePage gameId="g1" />);
    expect(screen.getByText(/Result 1-0/)).toBeInTheDocument();
    expect(screen.getByText("Reconnecting…")).toBeInTheDocument();
  });
});
