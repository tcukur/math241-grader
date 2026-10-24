#!/bin/bash
# Double-click to start MATH241 Grader on a Mac.
# The app is copied to this computer and runs from there, so nothing is ever written into this folder
# (safe to keep it in Google Drive or share it). The first start downloads what the app needs.
SRC="$(cd "$(dirname "$0")" && pwd)"
BASE="$HOME/Library/Application Support/MATH241 Grader"
APP="$BASE/app"
VENV="$BASE/venv"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1

fail() { echo; echo "$1"; echo; read -r -p "Press Enter to close this window." _; exit 1; }

# leftovers of older versions that ran inside this folder
[ -f "$SRC/.venv/pyvenv.cfg" ] && rm -rf "$SRC/.venv"
find "$SRC/grader_app" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null

echo "Copying the app to this computer..."
mkdir -p "$APP" || fail "Could not create $APP"
rm -rf "$APP/packs"   # older versions bundled an assignment here
for d in grader_app docs; do
  rm -rf "$APP/$d" && cp -R "$SRC/$d" "$APP/$d" \
    || fail "Could not copy the app from this folder. If it is in Google Drive, wait until it has finished syncing and try again."
done
cp -f "$SRC/run_grader.py" "$SRC/requirements-run.txt" "$APP/" || fail "Could not copy the app."
cd "$APP" || exit 1

if ! command -v uv >/dev/null 2>&1; then
  echo "First start: setting up MATH241 Grader. This happens only once and takes a few minutes."
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || fail "Could not download the setup tool. Check the internet connection and try again."
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! cmp -s requirements-run.txt "$VENV/.ready" || ! "$VENV/bin/python" -c "import PySide6, pymupdf" >/dev/null 2>&1; then
  echo "Preparing the app (one time)..."
  uv venv --quiet --clear --python 3.12 "$VENV" || fail "Could not prepare Python. Check the internet connection and try again."
  uv pip install --quiet --python "$VENV/bin/python" -r requirements-run.txt || fail "Could not install the app's parts. Check the internet connection and try again."
  cp requirements-run.txt "$VENV/.ready"
fi

echo "Starting MATH241 Grader. Leave this window open while you use the app."
"$VENV/bin/python" run_grader.py || fail "The app stopped with an error (shown above)."
