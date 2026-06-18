"""Go5x backend — FastAPI + KataGo via GTP protocol."""
from __future__ import annotations
import subprocess
import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BOARD_SIZE = 9
GTP_COLS = "ABCDEFGHJKLMNOPQRST"  # GTP skips 'I'


class PlayRequest(BaseModel):
    moves: list[list[int]]  # [[x, y], ...]


class Engine:
    def __init__(self):
        self.proc = None

    def start(self):
        katago = os.environ.get("KATAGO_PATH", "katago")
        model = os.environ.get("KATAGO_MODEL", "")
        config = os.environ.get("KATAGO_CONFIG", "")

        cmd = [katago, "gtp"]
        if model:
            cmd += ["-model", model]
        if config:
            cmd += ["-config", config]

        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        self._send("boardsize %d" % BOARD_SIZE)
        self._send("komi 7.5")
        self._send("clear_board")

    def _send(self, cmd: str) -> str:
        if not self.proc or self.proc.poll() is not None:
            raise RuntimeError("Engine not running")
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()
        lines = []
        while True:
            line = self.proc.stdout.readline()
            if line.strip() == "" and lines:
                break
            lines.append(line.strip())
        resp = "\n".join(lines)
        if resp.startswith("?"):
            raise RuntimeError(f"GTP error: {resp}")
        return resp.lstrip("= ").strip()

    def play(self, color: str, x: int, y: int):
        col = GTP_COLS[x]
        row = BOARD_SIZE - y
        self._send(f"play {color} {col}{row}")

    def play_pass(self, color: str):
        self._send(f"play {color} pass")

    def genmove(self, color: str) -> tuple[int, int] | None:
        resp = self._send(f"genmove {color}")
        if resp.lower() in ("pass", "resign"):
            return None
        col = GTP_COLS.index(resp[0].upper())
        row = int(resp[1:])
        return (col, BOARD_SIZE - row)

    def get_board_state(self) -> dict[str, list[list[int]]]:
        resp = self._send("showboard")
        black, white = [], []
        lines = resp.split("\n")
        for line in lines:
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            parts = line.split()
            row_num = int(parts[0])
            y = BOARD_SIZE - row_num
            for col_idx, ch in enumerate(parts[1:]):
                ch = ch.rstrip("0123456789")
                if ch == "X":
                    black.append([col_idx, y])
                elif ch == "O":
                    white.append([col_idx, y])
        return {"black": black, "white": white}

    def reset(self):
        self._send("clear_board")


engine = Engine()


@app.on_event("startup")
def startup():
    try:
        engine.start()
        print("KataGo engine started.")
    except Exception as e:
        print(f"WARNING: Could not start KataGo: {e}")
        print("Install KataGo first: brew install katago")


@app.post("/play")
def play(req: PlayRequest):
    if not engine.proc or engine.proc.poll() is not None:
        return {"error": "Engine not running. Install KataGo and restart."}

    try:
        # 1. Play all human (black) stones
        for x, y in req.moves:
            engine.play("black", x, y)

        # 2. Generate 5 AI (white) moves using pass trick
        ai_moves = []
        for i in range(5):
            move = engine.genmove("white")
            if move is None:
                break
            ai_moves.append(list(move))
            # Feed a black pass so AI gets another white turn (except after last)
            if i < 4:
                engine.play_pass("black")

        return {
            "ai_moves": ai_moves,
            "board": engine.get_board_state(),
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/reset")
def reset():
    try:
        engine.reset()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


app.mount("/", StaticFiles(directory=".", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
