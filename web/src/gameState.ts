/** Game data as the server sends it, plus the reducer that applies live events. */

export const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export type Result = "*" | "1-0" | "0-1" | "1/2-1/2";

export interface MoveRow {
  ply: number;
  san: string;
  uci: string;
  fen: string;
}

export interface GameSummary {
  id: string;
  event: string;
  white: string;
  black: string;
  result: Result;
  start_fen: string | null;
  ply: number;
  fen: string;
  created_at: string;
  updated_at: string;
}

export interface Game extends GameSummary {
  moves: MoveRow[];
}

export type ServerEvent =
  | { type: "snapshot"; game: Game }
  | { type: "move"; ply: number; san: string; uci: string; fen: string; result: Result };

export function applyEvent(state: Game | null, event: ServerEvent): Game | null {
  if (event.type === "snapshot") return event.game;
  if (state === null) return null;
  // Duplicates (a move that was also in the snapshot) and gaps are ignored; a reconnect resyncs.
  if (event.ply !== state.moves.length + 1) return state;
  const row: MoveRow = { ply: event.ply, san: event.san, uci: event.uci, fen: event.fen };
  return {
    ...state,
    moves: [...state.moves, row],
    ply: event.ply,
    fen: event.fen,
    result: event.result,
  };
}

/** Position to show: `viewPly` null means follow the live game. */
export function positionAt(game: Game, viewPly: number | null): { fen: string; lastMove?: string } {
  if (viewPly === null || viewPly >= game.moves.length) {
    const last = game.moves[game.moves.length - 1];
    return { fen: game.fen, lastMove: last?.uci };
  }
  if (viewPly <= 0) return { fen: game.start_fen ?? START_FEN };
  const row = game.moves[viewPly - 1];
  return { fen: row ? row.fen : game.fen, lastMove: row?.uci };
}

export function parseEvent(data: unknown): ServerEvent | null {
  if (typeof data !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (typeof parsed !== "object" || parsed === null) return null;
    const type = (parsed as { type?: unknown }).type;
    return type === "snapshot" || type === "move" ? (parsed as ServerEvent) : null;
  } catch {
    return null;
  }
}
