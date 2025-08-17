#!/usr/bin/env python3
# Displays a colored ASCII JSON video with optional scaling.
# Minimal:
#   python display.py --fit --loop
#   python display.py --scale 0.5   # downscale characters

import argparse
import json
import os
import sys
import time
import shutil

# Optional: Better ANSI support on Windows terminals.
try:
    import colorama
    colorama.just_fix_windows_console()
except Exception:
    pass

RESET = "\x1b[0m"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLS = "\x1b[2J"
HOME = "\x1b[H"

# Parse a line with ANSI SGR into per-cell (fg, char). Supports 38;2;r;g;b and 38;5;idx and 0 (reset).
def parse_ansi_line(ln: str):
    chars = []
    fgs = []  # None, ('truecolor', r, g, b), ('ansi256', idx)
    i = 0
    n = len(ln)
    active = None
    while i < n:
        ch = ln[i]
        if ch == "\x1b" and i + 1 < n and ln[i + 1] == "[":
            j = i + 2
            while j < n and ln[j] != "m":
                j += 1
            if j >= n:
                break
            params = ln[i + 2 : j]
            parts = params.split(";") if params else []
            if parts == ["0"]:
                active = None
            elif len(parts) >= 3 and parts[0] == "38" and parts[1] == "5":
                try:
                    idx = int(parts[2])
                    active = ("ansi256", idx)
                except Exception:
                    pass
            elif len(parts) >= 5 and parts[0] == "38" and parts[1] == "2":
                try:
                    r = int(parts[2]); g = int(parts[3]); b = int(parts[4])
                    active = ("truecolor", r, g, b)
                except Exception:
                    pass
            i = j + 1
            continue
        else:
            if ch != "\n":
                chars.append(ch)
                fgs.append(active)
            i += 1
    return chars, fgs

def color_code_from_fg(fg):
    if fg is None:
        return ""
    if fg[0] == "truecolor":
        _, r, g, b = fg
        return f"\x1b[38;2;{r};{g};{b}m"
    if fg[0] == "ansi256":
        _, idx = fg
        return f"\x1b[38;5;{idx}m"
    return ""

def scale_lines(lines, width, height, scale, fit_to_terminal):
    # Decide scale
    if fit_to_terminal:
        term = shutil.get_terminal_size(fallback=(80, 24))
        s_w = term.columns / max(1, width)
        s_h = max(1, term.lines - 1) / max(1, height)
        s = min(s_w, s_h)
        if s <= 0:
            s = 1.0
    else:
        s = max(0.01, float(scale))

    if abs(s - 1.0) < 1e-6:
        return lines

    parsed = [parse_ansi_line(ln) for ln in lines]
    src_h = len(parsed)
    src_w = len(parsed[0][0]) if parsed else 0
    if src_w == 0:
        src_w = max(1, width)
    if src_h == 0:
        src_h = max(1, height)

    tgt_w = max(1, int(src_w * s))
    tgt_h = max(1, int(src_h * s))

    new_lines = []
    for ro in range(tgt_h):
        rs = min(src_h - 1, int(ro / s))
        chars_row, fgs_row = parsed[rs]
        row_w = len(chars_row)
        if row_w == 0:
            new_lines.append(RESET)
            continue
        tgt_w_row = max(1, int(row_w * s))
        parts = []
        prev_fg = None
        for co in range(tgt_w_row):
            cs = min(row_w - 1, int(co / s))
            fg = fgs_row[cs]
            ch = chars_row[cs]
            if fg != prev_fg:
                parts.append(RESET if fg is None else color_code_from_fg(fg))
                prev_fg = fg
            parts.append(ch)
        parts.append(RESET)
        new_lines.append("".join(parts))
    return new_lines

def main():
    parser = argparse.ArgumentParser(description="Play a colored ASCII JSON video in your terminal.")
    parser.add_argument("--input", default="out.json", help="Input JSON file (default: out.json)")
    parser.add_argument("--loop", action="store_true", help="Loop playback")
    parser.add_argument("--scale", type=float, default=1.0, help="Scale factor (<1 downscale, >1 upscale). Ignored if --fit is used.")
    parser.add_argument("--fit", action="store_true", help="Automatically scale to fit the current terminal")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear the screen at start")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: input JSON not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    frames = data.get("frames", [])
    if not frames:
        print("No frames in JSON.")
        sys.exit(1)

    width = int(data.get("width", 0))
    height = int(data.get("height", 0))
    use_fps = float(data.get("fps", 30.0)) or 30.0
    frame_dt = 1.0 / use_fps

    out = sys.stdout
    out.write(HIDE_CURSOR)
    if not args.no_clear:
        out.write(CLS)
    out.write(HOME)
    out.flush()

    try:
        idx = 0
        start_time = time.perf_counter()
        while True:
            frame = frames[idx]
            lines = frame.get("lines", [])

            if args.fit or abs(args.scale - 1.0) > 1e-6:
                lines = scale_lines(lines, width, height, args.scale, args.fit)

            out.write(HOME)
            for ln in lines:
                out.write(ln)
                out.write("\n")
            out.flush()

            idx += 1
            if idx >= len(frames):
                if args.loop:
                    idx = 0
                    start_time = time.perf_counter()
                else:
                    break

            next_time = start_time + idx * frame_dt
            sleep_for = next_time - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)

    except KeyboardInterrupt:
        pass
    finally:
        out.write(RESET)
        out.write(SHOW_CURSOR)
        out.flush()

if __name__ == "__main__":
    main()