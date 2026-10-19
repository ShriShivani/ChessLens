import { useEffect, useState } from "react";
import { pgnUrl } from "../api";
import { positionAt } from "../gameState";
import { useGameSocket, type ConnectionStatus } from "../useGameSocket";
import BoardView from "./BoardView";
import MoveList from "./MoveList";

const STATUS_TEXT: Record<ConnectionStatus, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
  notfound: "Game not found",
};

export default function GamePage({ gameId }: { gameId: string }) {
  const { game, status } = useGameSocket(gameId);
  const [viewPly, setViewPly] = useState<number | null>(null); // null = follow live
  const [flipped, setFlipped] = useState(false);

  const total = game?.moves.length ?? 0;
  const shown = viewPly === null ? total : Math.min(viewPly, total);

  const go = (ply: number) => setViewPly(ply >= total ? null : Math.max(0, ply));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") go(shown - 1);
      else if (e.key === "ArrowRight") go(shown + 1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (status === "notfound") {
    return (
      <main className="page">
        <p role="alert">Game “{gameId}” was not found.</p>
        <a href="#/">Back to games</a>
      </main>
    );
  }
  if (!game) {
    return (
      <main className="page">
        <p className="muted" role="status">
          {STATUS_TEXT[status]}
        </p>
      </main>
    );
  }

  const pos = positionAt(game, viewPly);
  const following = viewPly === null;

  return (
    <main className="page game">
      <header className="game-head">
        <a href="#/" className="back">
          ← Games
        </a>
        <h1>
          {game.white} <span className="muted">vs</span> {game.black}
        </h1>
        <p className="muted">
          {game.event} ·{" "}
          <span className={`chip ${status}`} role="status">
            {STATUS_TEXT[status]}
          </span>
          {game.result !== "*" && <strong className="result"> · Result {game.result}</strong>}
        </p>
      </header>

      <section className="board-col">
        <BoardView
          fen={pos.fen}
          lastMove={pos.lastMove}
          orientation={flipped ? "black" : "white"}
        />
        <div className="controls">
          <button onClick={() => go(0)} disabled={shown === 0} aria-label="First move">
            ⏮
          </button>
          <button onClick={() => go(shown - 1)} disabled={shown === 0} aria-label="Previous move">
            ◀
          </button>
          <button onClick={() => go(shown + 1)} disabled={following} aria-label="Next move">
            ▶
          </button>
          <button onClick={() => setViewPly(null)} disabled={following} aria-label="Latest move">
            ⏭
          </button>
          <button onClick={() => setFlipped((f) => !f)} aria-label="Flip board">
            ⇅
          </button>
        </div>
      </section>

      <section className="side-col">
        <MoveList moves={game.moves} current={shown} onSelect={go} />
        <a className="button" href={pgnUrl(game.id)} download>
          Download PGN
        </a>
      </section>
    </main>
  );
}
