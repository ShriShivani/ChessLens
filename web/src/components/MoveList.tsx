import { useEffect, useRef } from "react";
import type { MoveRow } from "../gameState";

interface Props {
  moves: MoveRow[];
  /** Ply being shown (0 = start). */
  current: number;
  onSelect: (ply: number) => void;
}

export default function MoveList({ moves, current, onSelect }: Props) {
  const active = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    active.current?.scrollIntoView?.({ block: "nearest" });
  }, [current]);

  if (moves.length === 0) return <p className="muted">No moves yet.</p>;

  const rows: MoveRow[][] = [];
  for (let i = 0; i < moves.length; i += 2) rows.push(moves.slice(i, i + 2));

  return (
    <ol className="moves" aria-label="Moves">
      {rows.map((pair, i) => (
        <li key={i}>
          <span className="move-no">{i + 1}.</span>
          {pair.map((m) => (
            <button
              key={m.ply}
              ref={m.ply === current ? active : undefined}
              className={m.ply === current ? "move active" : "move"}
              aria-current={m.ply === current ? "true" : undefined}
              onClick={() => onSelect(m.ply)}
            >
              {m.san}
            </button>
          ))}
        </li>
      ))}
    </ol>
  );
}
