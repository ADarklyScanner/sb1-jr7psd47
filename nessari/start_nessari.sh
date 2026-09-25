#!/data/data/com.termux/files/usr/bin/bash
# One tap: start Nessari's server (if it isn't already running) and open her
# in Firefox Focus, which keeps no history, cookies or saved data.
#
# Install as a home-screen button (needs the Termux:Widget app):
#   mkdir -p ~/.shortcuts && cp start_nessari.sh ~/.shortcuts/Nessari && chmod +x ~/.shortcuts/Nessari
# Stop her later with:  pkill -f llama-server

MODEL=~/models/Llama-3.2-3B-Instruct-Q4_0.gguf
URL=http://127.0.0.1:8080
LOG=~/chatbot/server.log

up() { curl -s -m 2 "$URL/health" | grep -q ok; }

if ! up; then
  termux-wake-lock
  cd ~/llama.cpp || exit 1
  nohup ./build/bin/llama-server -m "$MODEL" --path ~/chatbot \
    -c 16384 -t 6 --parallel 1 > "$LOG" 2>&1 &
  echo "Starting Nessari..."
  for _ in $(seq 60); do
    up && break
    sleep 1
  done
  if ! up; then
    echo "Server didn't start. Last lines of $LOG:"
    tail -n 20 "$LOG"
    exit 1
  fi
fi

# Firefox Focus if installed, otherwise the default browser.
# (am can exit 0 even when it fails, so check its output for "Error".)
if am start -a android.intent.action.VIEW -d "$URL" -p org.mozilla.focus 2>&1 | grep -q Error; then
  termux-open-url "$URL"
fi
