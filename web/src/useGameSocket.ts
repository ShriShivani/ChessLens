import { useEffect, useState } from "react";
import { gameMissing, wsUrl } from "./api";
import { applyEvent, parseEvent, type Game } from "./gameState";

export type ConnectionStatus = "connecting" | "live" | "reconnecting" | "notfound";

const NOT_FOUND_CODE = 4404;

/** 1s, 2s, 4s ... capped at 10s. */
export function backoffMs(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 10_000);
}

export function useGameSocket(gameId: string): { game: Game | null; status: ConnectionStatus } {
  const [game, setGame] = useState<Game | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let stopped = false;
    let everLive = false;

    const connect = () => {
      socket = new WebSocket(wsUrl(`/ws/games/${encodeURIComponent(gameId)}`));
      socket.onmessage = (msg: MessageEvent) => {
        const event = parseEvent(msg.data);
        if (!event) return;
        attempt = 0;
        everLive = true;
        setStatus("live");
        setGame((prev) => applyEvent(prev, event));
      };
      socket.onclose = async (ev: CloseEvent) => {
        if (stopped) return;
        if (ev.code === NOT_FOUND_CODE || (!everLive && (await gameMissing(gameId)))) {
          if (!stopped) setStatus("notfound");
          return;
        }
        if (stopped) return;
        setStatus("reconnecting");
        timer = setTimeout(connect, backoffMs(attempt++));
      };
    };

    setGame(null);
    setStatus("connecting");
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [gameId]);

  return { game, status };
}
