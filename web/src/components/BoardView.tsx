import { Chessground } from "chessground";
import type { Api } from "chessground/api";
import type { Key } from "chessground/types";
import { useEffect, useRef } from "react";

import "chessground/assets/chessground.base.css";
import "chessground/assets/chessground.brown.css";
import "chessground/assets/chessground.cburnett.css";

interface Props {
  fen: string;
  lastMove?: string; // UCI, e.g. "e2e4"
  orientation: "white" | "black";
}

function toKeys(uci?: string): Key[] | undefined {
  return uci ? [uci.slice(0, 2) as Key, uci.slice(2, 4) as Key] : undefined;
}

/** Read-only chessground board that follows its props. */
export default function BoardView({ fen, lastMove, orientation }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<Api | null>(null);

  useEffect(() => {
    if (!host.current) return;
    api.current = Chessground(host.current, {
      fen,
      orientation,
      lastMove: toKeys(lastMove),
      viewOnly: true,
      coordinates: true,
      animation: { enabled: true, duration: 200 },
    });
    return () => api.current?.destroy();
    // Created once; later prop changes are applied by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    api.current?.set({ fen, orientation, lastMove: toKeys(lastMove) });
  }, [fen, lastMove, orientation]);

  return <div className="board" ref={host} role="img" aria-label={`Chess position ${fen}`} />;
}
