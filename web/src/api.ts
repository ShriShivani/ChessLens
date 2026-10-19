import type { GameSummary } from "./gameState";

/** Empty by default: the page and API share an origin (Vite proxy in dev, nginx in compose). */
const API_BASE: string = import.meta.env.VITE_API_URL ?? "";

export function pgnUrl(gameId: string): string {
  return `${API_BASE}/api/games/${encodeURIComponent(gameId)}/pgn`;
}

export function wsUrl(path: string): string {
  const override: string | undefined = import.meta.env.VITE_WS_URL;
  if (override) return `${override}${path}`;
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}${path}`;
}

export async function fetchGames(signal?: AbortSignal): Promise<GameSummary[]> {
  const res = await fetch(`${API_BASE}/api/games`, { signal });
  if (!res.ok) throw new Error(`server returned ${res.status}`);
  return (await res.json()) as GameSummary[];
}

/** A refused WebSocket handshake hides the close code from browsers, so ask over REST. */
export async function gameMissing(gameId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/games/${encodeURIComponent(gameId)}`);
    return res.status === 404;
  } catch {
    return false;
  }
}
