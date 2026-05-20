#!/usr/bin/env python3
"""Real-time usage status line for Claude Code.

Configurable columns. Pass --columns=<csv> to choose which fields to show
and in what order. Available columns:

  model    bold cyan model display name
  ctx      live context-window usage (bar + % + token count, color-coded)
  cost     session cost in USD (2 decimals if ≥ $0.01, else 4)
  tokens   cumulative Σ in / out / cache_r / cache_w
  diff     lines added/removed (+N -M)
  api      cumulative API time in seconds
  cwd      basename of the working directory

CLI flags (parsed by hand; no argparse dependency):

  --columns=model,ctx,cost,diff,api,cwd   default
  --sep=" │ "                              separator between fields
  --no-color                               strip ANSI (e.g. for piping/tests)

These can also be set via env vars CC_STATUSLINE_COLUMNS and CC_STATUSLINE_SEP
for users who'd rather configure once in their shell rc.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_COLUMNS = "model,ctx,cost,diff,api,cwd"
DEFAULT_SEP = " │ "

# Context window per model id. Anything not listed falls back to 200k unless
# the payload signals exceeds_200k_tokens.
CONTEXT_LIMITS = {
    "claude-opus-4-7": 200_000,
    "claude-opus-4-7[1m]": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-sonnet-4-6[1m]": 1_000_000,
    "claude-haiku-4-5": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
}
DEFAULT_LIMIT = 200_000

# ---- ANSI ----
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RESET = "\033[0m"


def fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def pick_color(pct: float, scale: tuple[float, float] = (50.0, 80.0)) -> str:
    if pct < scale[0]:
        return GREEN
    if pct < scale[1]:
        return YELLOW
    return RED


def parse_transcript(path: str | None) -> dict | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None

    last_usage: dict | None = None
    total_input = 0
    total_output = 0
    total_cache_create = 0
    total_cache_read = 0

    try:
        with p.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = (entry.get("message") or {}).get("usage")
                if not isinstance(usage, dict):
                    continue
                last_usage = usage
                total_input += int(usage.get("input_tokens", 0) or 0)
                total_output += int(usage.get("output_tokens", 0) or 0)
                total_cache_create += int(usage.get("cache_creation_input_tokens", 0) or 0)
                total_cache_read += int(usage.get("cache_read_input_tokens", 0) or 0)
    except OSError:
        return None

    return {
        "last": last_usage,
        "total_input": total_input,
        "total_output": total_output,
        "total_cache_create": total_cache_create,
        "total_cache_read": total_cache_read,
    }


# ---- column renderers ----
# Each takes the prepared context dict and returns a string (or None to skip).

def col_model(c: dict) -> str | None:
    label = c["model_label"]
    return f"{BOLD}{CYAN}{label}{RESET}" if label else None


def col_ctx(c: dict) -> str | None:
    usage = c["usage"]
    if not usage or not isinstance(usage.get("last"), dict):
        return None
    last = usage["last"]
    ctx_now = (
        int(last.get("input_tokens", 0) or 0)
        + int(last.get("cache_read_input_tokens", 0) or 0)
        + int(last.get("cache_creation_input_tokens", 0) or 0)
    )
    limit = c["limit"]
    pct = (ctx_now / limit * 100.0) if limit else 0.0
    color = pick_color(pct)
    bar_width = 10
    filled = max(0, min(bar_width, int(round(pct / 100.0 * bar_width))))
    bar = "█" * filled + "░" * (bar_width - filled)
    return f"{color}ctx {bar} {pct:.0f}% ({fmt_num(ctx_now)}){RESET}"


def col_cost(c: dict) -> str | None:
    v = c["cost_usd"]
    if v <= 0:
        return None
    fmt = f"${v:.2f}" if v >= 0.01 else f"${v:.4f}"
    return f"{MAGENTA}{fmt}{RESET}"


def col_tokens(c: dict) -> str | None:
    usage = c["usage"]
    if not usage:
        return None
    tot_in = usage["total_input"]
    tot_out = usage["total_output"]
    tot_cr = usage["total_cache_read"]
    tot_cc = usage["total_cache_create"]
    if not (tot_in or tot_out or tot_cr or tot_cc):
        return None
    return (
        f"{DIM}Σ in {fmt_num(tot_in)} · out {fmt_num(tot_out)} · "
        f"cache_r {fmt_num(tot_cr)} · cache_w {fmt_num(tot_cc)}{RESET}"
    )


def col_diff(c: dict) -> str | None:
    a, r = c["lines_added"], c["lines_removed"]
    if not (a or r):
        return None
    return f"{DIM}{GREEN}+{a}{RESET}{DIM} {RED}-{r}{RESET}"


def col_api(c: dict) -> str | None:
    ms = c["api_ms"]
    return f"{DIM}api {ms / 1000:.1f}s{RESET}" if ms else None


def col_cwd(c: dict) -> str | None:
    return f"{DIM}{BLUE}{c['cwd_base']}{RESET}" if c["cwd_base"] else None


COLUMNS = {
    "model": col_model,
    "ctx": col_ctx,
    "cost": col_cost,
    "tokens": col_tokens,
    "diff": col_diff,
    "api": col_api,
    "cwd": col_cwd,
}


# ---- arg parsing ----
def parse_args(argv: list[str]) -> dict:
    out = {
        "columns": os.environ.get("CC_STATUSLINE_COLUMNS", DEFAULT_COLUMNS),
        "sep": os.environ.get("CC_STATUSLINE_SEP", DEFAULT_SEP),
        "color": True,
    }
    for arg in argv:
        if arg.startswith("--columns="):
            out["columns"] = arg[len("--columns="):]
        elif arg.startswith("--sep="):
            out["sep"] = arg[len("--sep="):]
        elif arg == "--no-color":
            out["color"] = False
    return out


def strip_ansi(s: str) -> str:
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)


def main() -> int:
    args = parse_args(sys.argv[1:])

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    model = payload.get("model") or {}
    model_id = model.get("id") or ""
    model_label = model.get("display_name") or model_id or "?"
    # trim verbose suffix so the status line stays compact
    model_label = model_label.replace(" context)", ")")

    cost = payload.get("cost") or {}
    cwd = payload.get("cwd") or os.getcwd()

    limit = CONTEXT_LIMITS.get(model_id, DEFAULT_LIMIT)
    if payload.get("exceeds_200k_tokens") and limit <= 200_000:
        limit = 1_000_000

    ctx_data = {
        "model_label": model_label,
        "model_id": model_id,
        "limit": limit,
        "cost_usd": float(cost.get("total_cost_usd") or 0.0),
        "api_ms": int(cost.get("total_api_duration_ms") or 0),
        "lines_added": int(cost.get("total_lines_added") or 0),
        "lines_removed": int(cost.get("total_lines_removed") or 0),
        "cwd_base": os.path.basename(cwd.rstrip("/")) or cwd,
        "usage": parse_transcript(payload.get("transcript_path")),
    }

    cols = [c.strip() for c in args["columns"].split(",") if c.strip()]
    parts: list[str] = []
    for name in cols:
        renderer = COLUMNS.get(name)
        if not renderer:
            continue
        out = renderer(ctx_data)
        if out:
            parts.append(out)

    line = args["sep"].join(parts)
    if not args["color"]:
        line = strip_ansi(line)

    sys.stdout.write(line)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
