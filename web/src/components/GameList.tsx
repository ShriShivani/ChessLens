import { useCallback, useEffect, useState } from "react";
import { fetchGames } from "../api";
import type { GameSummary } from "../gameState";

const REFRESH_MS = 10_000;

export default function GameList() {
  const [games, setGames] = useState<GameSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setGames(await fetchGames(signal));
      setError(null);
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof Error ? e.message : "could not load games");
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);
    const id = setInterval(() => void load(ctrl.signal), REFRESH_MS);
    return () => {
      ctrl.abort();
      clearInterval(id);
    };
  }, [load]);

  return (
    <main className="page">
      <h1>ChessLens</h1>
      <p className="muted">Live games from physical boards.</p>
      {error && (
        <p role="alert" className="error">
          Could not load games: {error}.{" "}
          <button onClick={() => void load()}>Retry</button>
        </p>
      )}
      {games === null && !error && <p className="muted">Loading…</p>}
      {games?.length === 0 && <p className="muted">No games yet.</p>}
      <ul className="game-list">
        {games?.map((g) => (
          <li key={g.id}>
            <a href={`#/game/${g.id}`}>
              <strong>
                {g.white} vs {g.black}
              </strong>
              <span className="muted">
                {g.event} · {g.ply} {g.ply === 1 ? "move" : "moves"} ·{" "}
                {g.result === "*" ? "in progress" : g.result}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
