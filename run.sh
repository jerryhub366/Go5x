#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate

export KATAGO_PATH="katago"
export KATAGO_MODEL="/opt/homebrew/share/katago/g170e-b20c256x2-s5303129600-d1228401921.bin.gz"
export KATAGO_CONFIG="/opt/homebrew/share/katago/configs/gtp_example.cfg"

echo "Starting Go5x on http://localhost:8000"
python server.py
