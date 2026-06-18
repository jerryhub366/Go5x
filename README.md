# Go5x

A modified Go (围棋) game where **each player places 5 stones per turn**.

Captures, liberties, and ko rules work exactly like standard Go — the only twist is the 5-stones-per-turn mechanic.

## How it works

- **Human (Black):** Click 5 positions on the board. Each stone is sent to the engine immediately, so captures happen in real-time as you place.
- **AI (White):** After your 5 stones, KataGo generates 5 responses using a pass-trick hack (no engine modification needed).
- No score counting, no pass — just play and refresh to restart.

## Tech Stack

- **Frontend:** Single-file HTML/JS with [WGo.js](https://github.com/waltheri/wgo.js) for board rendering
- **Backend:** Python FastAPI wrapping [KataGo](https://github.com/lightvector/KataGo) via GTP protocol

## Quick Start

```bash
# Install dependencies
brew install katago
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi 'uvicorn[standard]'

# Run
bash run.sh
# Open http://localhost:8000
```

## The Pass Trick

To get 5 consecutive AI moves without modifying KataGo's source:

1. Play all 5 human (black) stones in the engine
2. Ask AI to generate a white move
3. Feed `play black pass` to the engine
4. Repeat steps 2-3 until 5 white moves are collected

The AI thinks black is passing each time, so it happily plays another white stone.
