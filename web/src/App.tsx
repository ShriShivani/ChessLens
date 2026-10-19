import { useEffect, useState } from "react";
import GameList from "./components/GameList";
import GamePage from "./components/GamePage";

/** Hash routes keep the build static: `#/` lists games, `#/game/<id>` shows one. */
export function parseRoute(hash: string): { page: "list" } | { page: "game"; id: string } {
  const match = /^#\/game\/([^/?#]+)/.exec(hash);
  return match?.[1] ? { page: "game", id: decodeURIComponent(match[1]) } : { page: "list" };
}

export default function App() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const route = parseRoute(hash);
  return route.page === "game" ? <GamePage key={route.id} gameId={route.id} /> : <GameList />;
}
