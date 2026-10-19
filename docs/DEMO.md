# Demo script (about 2 minutes)

Goal: show a physical game appearing live on a web page, then show that it recovers from
mistakes. Rehearse once; keep the camera and board still.

## Setup (before recording)

1. Board on a plain surface, camera overhead or steep, even light, no glare.
2. Start the stack: `docker compose up --build`, or the local commands in the runbook.
3. Calibrate: `python -m edge calibrate --source 0`.
4. Open the web app on a second screen or on a phone on the same network.

## Script

1. **(0:00)** "This is a normal chessboard and a phone camera. No sensor board."
   Show the board and the empty game list in the browser.
2. **(0:15)** Start the client with `--server ...`. It prints the viewer link; open it.
   The page shows the starting position and "Live".
3. **(0:25)** Play 1.e4 e5 2.Nf3 Nc6. Each move appears in the browser a moment after the
   hand leaves the board. Point at the move list.
4. **(0:50)** Play a capture and castle. Say: "It does not recognise pieces. It knows the
   position and asks which legal move explains what changed."
5. **(1:10)** Make an ambiguous change on purpose (slide a piece out of its square and put it
   back crookedly or cover two squares). The client says UNCERTAIN with candidates; press the
   matching number key. Say: "When it is not sure it asks instead of guessing."
6. **(1:30)** Press `u` to undo a move and replay it: the web page follows.
7. **(1:40)** Pull the network cable or turn Wi-Fi off, play a move, turn it back on: the move
   arrives. Say: "Moves are queued and reconciled on reconnect."
8. **(1:50)** Click a move in the list to step back, click Download PGN, open it.
9. **(2:00)** Show the accuracy page and say plainly which numbers are synthetic and which
   are real.

## Backup plan

If the camera misbehaves, play a recorded clip instead:
`python -m edge run --source tests/real/clip.mp4 --calibration tests/real/clip.calibration.json --server ... --token ...`
