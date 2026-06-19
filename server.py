"""Go5x backend — FastAPI + KataGo via GTP protocol."""
from __future__ import annotations
import subprocess
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BOARD_SIZE = 9
GTP_COLS = "ABCDEFGHJKLMNOPQRST"  # GTP skips 'I'


class PlaceRequest(BaseModel):
    x: int
    y: int


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
        # GTP responses end with two consecutive newlines (blank line after content).
        # Read until we see a blank line AFTER the "= " or "? " response header.
        lines = []
        saw_header = False
        while True:
            line = self.proc.stdout.readline()
            if not line:
                break
            stripped = line.rstrip("\n\r")
            if not saw_header:
                if stripped.startswith("= ") or stripped.startswith("=\n") or stripped == "=" or stripped.startswith("?"):
                    saw_header = True
                    lines.append(stripped)
                continue
            if stripped == "":
                break
            lines.append(stripped)
        resp = "\n".join(lines)
        if resp.startswith("?"):
            raise RuntimeError(f"GTP error: {resp}")
        return resp.lstrip("= ").strip()

    def _try_send(self, cmd: str) -> tuple[bool, str]:
        try:
            return True, self._send(cmd)
        except RuntimeError as e:
            return False, str(e)

    def play(self, color: str, x: int, y: int) -> bool:
        col = GTP_COLS[x]
        row = BOARD_SIZE - y
        ok, _ = self._try_send(f"play {color} {col}{row}")
        return ok

    def play_pass(self, color: str):
        self._send(f"play {color} pass")

    def genmove(self, color: str) -> tuple[int, int] | None:
        resp = self._send(f"genmove {color}")
        if not resp or resp.lower() in ("pass", "resign"):
            return None
        col = GTP_COLS.index(resp[0].upper())
        row = int(resp[1:])
        return (col, BOARD_SIZE - row)

    def get_board_state(self) -> dict[str, list[list[int]]]:
        import re
        resp = self._send("showboard")
        black, white = [], []
        for line in resp.split("\n"):
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            parts = line.split()
            row_num = int(parts[0])
            y = BOARD_SIZE - row_num
            # Rejoin and split by known cell patterns to handle "X1." gluing
            row_str = " ".join(parts[1:])
            cells = re.findall(r'[XO]\d*|\.', row_str)
            for col_idx, cell in enumerate(cells):
                if cell.startswith("X"):
                    black.append([col_idx, y])
                elif cell.startswith("O"):
                    white.append([col_idx, y])
        return {"black": black, "white": white}

    def undo(self):
        self._try_send("undo")

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


@app.post("/place")
def place_stone(req: PlaceRequest):
    """Place a single black stone and return updated board state."""
    if not engine.proc or engine.proc.poll() is not None:
        return {"error": "Engine not running."}
    try:
        if not engine.play("black", req.x, req.y):
            return {"error": f"非法落子 ({req.x},{req.y})", "board": engine.get_board_state()}
        return {"ok": True, "board": engine.get_board_state()}
    except Exception as e:
        try:
            board = engine.get_board_state()
        except Exception:
            board = None
        return {"error": str(e), "board": board}


@app.post("/ai_turn")
def ai_turn():
    """Generate 5 AI (white) moves using pass trick. Retries on pass/resign."""
    if not engine.proc or engine.proc.poll() is not None:
        return {"error": "Engine not running."}
    try:
        ai_moves = []
        max_attempts = 12
        attempts = 0
        while len(ai_moves) < 5 and attempts < max_attempts:
            move = engine.genmove("white")
            attempts += 1
            if move is None:
                # AI passed or resigned — undo and feed black pass to retry
                engine.undo()
                if len(ai_moves) < 5:
                    engine.play_pass("white")
                    engine.play_pass("black")
                continue
            ai_moves.append(list(move))
            if len(ai_moves) < 5:
                engine.play_pass("black")

        return {
            "ai_moves": ai_moves,
            "board": engine.get_board_state(),
        }
    except Exception as e:
        try:
            board = engine.get_board_state()
        except Exception:
            board = None
        return {"error": str(e), "board": board}


@app.post("/undo")
def undo_move():
    try:
        engine.undo()
        return {"ok": True, "board": engine.get_board_state()}
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
