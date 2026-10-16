"""Terminal screenshot as SVG, from a tmux pane: `tmux capture-pane -ep -t <pane> | python scripts/capture_svg.py out.svg`.

Each character goes in its own cell (Hangul and other wide characters take two), so the picture lines up the way the terminal
does, whatever font the viewer has. Colours: the SGR codes tmux emits (30-37, 90-97, 38;5;n, bold, dim).
"""
import html, re, sys, unicodedata

BG, FG = "#1e1f26", "#d4d4d4"
BASE = ["#1e1f26", "#e06c75", "#7fb069", "#d7a65f", "#61afef", "#c678dd", "#56b6c2", "#d4d4d4"]
BRIGHT = ["#7f848e", "#ef8a91", "#98c379", "#e5c07b", "#82c0ff", "#d79bea", "#7fd0da", "#ffffff"]
CW, CH, FS = 8.4, 18, 14


def wide(c): return unicodedata.east_asian_width(c) in "WF"


def xterm(n):
    if n < 8: return BASE[n]
    if n < 16: return BRIGHT[n - 8]
    if n >= 232: v = 8 + 10 * (n - 232); return f"#{v:02x}{v:02x}{v:02x}"
    n -= 16; r, g, b = n // 36, n // 6 % 6, n % 6; f = lambda v: 0 if v == 0 else 55 + 40 * v
    return f"#{f(r):02x}{f(g):02x}{f(b):02x}"


def cells(text):
    """-> rows of (char, fg, bold, dim) per cell; a wide char's second cell is None."""
    rows = []
    for line in text.rstrip("\n").split("\n"):
        fg, bold, dim, row = None, False, False, []
        for seg in re.split(r"(\x1b\[[\d;]*m)", line):
            m = re.fullmatch(r"\x1b\[([\d;]*)m", seg)
            if m:
                codes = [int(c) if c else 0 for c in m.group(1).split(";")]; k = 0
                while k < len(codes):
                    c = codes[k]
                    if c == 0: fg, bold, dim = None, False, False
                    elif c == 1: bold = True
                    elif c == 2: dim = True
                    elif c == 22: bold = dim = False
                    elif c == 39: fg = None
                    elif 30 <= c <= 37: fg = BASE[c - 30]
                    elif 90 <= c <= 97: fg = BRIGHT[c - 90]
                    elif c == 38 and k + 2 < len(codes) and codes[k + 1] == 5: fg = xterm(codes[k + 2]); k += 2
                    k += 1
                continue
            for ch in seg:
                row.append((ch, fg, bold, dim))
                if wide(ch): row.append(None)
        rows.append(row)
    return rows


def svg(rows):
    w = max((len(r) for r in rows), default=1); h = len(rows)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * CW + 24:.0f}" height="{h * CH + 24}" '
           f'font-family="DejaVu Sans Mono, Menlo, Consolas, monospace" font-size="{FS}">',
           f'<rect width="100%" height="100%" rx="8" fill="{BG}"/>']
    for y, row in enumerate(rows):
        runs = []                                                   # same style in a row: one <text> with an x per character
        for x, c in enumerate(row):
            if not c or c[0] == " ": continue
            if runs and runs[-1][0] == c[1:]: runs[-1][1].append((x, c[0]))
            else: runs.append((c[1:], [(x, c[0])]))
        for (fg, bold, dim), chars in runs:
            attrs = f'fill="{fg or FG}"' + (' font-weight="bold"' if bold else "") + (' opacity="0.55"' if dim else "")
            xs = " ".join(f"{12 + x * CW:.1f}" for x, _ in chars)
            out.append(f'<text x="{xs}" y="{12 + y * CH + FS:.0f}" {attrs}>{html.escape("".join(ch for _, ch in chars))}</text>')
    return "\n".join(out + ["</svg>"])


if __name__ == "__main__":
    open(sys.argv[1], "w", encoding="utf-8").write(svg(cells(sys.stdin.read())))
