#!/usr/bin/env bash
# Install the Claude Code realtime-usage status line.
#
# What it does:
#   1) copies statusline.py into ~/.claude/statusline.py
#   2) merges a "statusLine" stanza into ~/.claude/settings.json
#      (creates the file if missing, leaves all other keys intact)
#
# Idempotent: re-running just refreshes the script + statusLine config.
# Non-invasive: never touches the Claude Code app bundle.

set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SRC_DIR/statusline.py"
DEST_DIR="$HOME/.claude"
DEST="$DEST_DIR/statusline.py"
SETTINGS="$DEST_DIR/settings.json"

if [[ ! -f "$SRC" ]]; then
  echo "error: $SRC not found" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
install -m 0755 "$SRC" "$DEST"
echo "installed: $DEST"

# Merge settings.json via python (no jq dependency).
python3 - "$SETTINGS" <<'PY'
import json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        backup = path + ".bak"
        os.rename(path, backup)
        print(f"warning: {path} was not valid JSON, backed up to {backup}", file=sys.stderr)
        data = {}

data["statusLine"] = {
    "type": "command",
    "command": "$HOME/.claude/statusline.py",
    "padding": 0,
}

with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"patched: {path}")
PY

echo "done. Restart any open Claude Code sessions to see the status line."
