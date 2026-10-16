"""Motion for the terminal screens.

`Win` wraps the curses window (or the Windows stand-in, term._Screen). Screens draw as before: text goes through
addstr, then refresh shows the frame. The wrapper records what a frame draws, and when a transition was armed with
`transition(kind)` it plays the recorded frame over a few short frames before showing it as drawn:

    slide     the new step comes in from the right (dir=1) or from the left (dir=-1)     160 ms
    wipe      the frame is uncovered from left to right (the logo being drawn)            420 ms
    cascade   rows appear one after another from the top                                  220 ms

Rows 0-3 (brand, nav buttons, rule) never move. `y_from` limits a transition to the rows below it. Nothing is animated
when ADC_MOTION=0 or stdout is not a terminal (tests, pipes), so screens behave exactly as without motion.
"""
import os, sys, time, unicodedata

FIXED_ROWS = 4
FPS = 30
DURATION = {"slide": 0.16, "wipe": 0.42, "cascade": 0.22}


def enabled():
    return os.environ.get("ADC_MOTION", "1") != "0" and sys.stdout.isatty()


def ease(t):
    """ease-out cubic: fast start, soft landing."""
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3


def _cw(c): return 2 if unicodedata.east_asian_width(c) in "WF" else 1


def _window(s, x, lo, hi):
    """the part of text s drawn from column x that falls in display columns [lo, hi) -> (new x, text)."""
    out, col, start = "", x, None
    for ch in s:
        w = _cw(ch)
        if col >= lo and col + w <= hi:
            if start is None: start = col
            out += ch
        col += w
    return start, out


class Win:
    def __init__(self, win):
        self._w = win; self._ops = []; self._kind = None; self._opts = {}

    def __getattr__(self, name): return getattr(self._w, name)

    def transition(self, kind, **opts):
        """arm a transition for the next refresh (ignored when motion is off)."""
        if enabled(): self._kind, self._opts = kind, opts

    def armed(self): return self._kind is not None

    def erase(self): self._ops = []; self._w.erase()
    clear = erase

    def addstr(self, y, x, s, attr=0):
        self._ops.append((y, x, s, attr)); self._w.addstr(y, x, s, attr)

    def refresh(self):
        kind, self._kind = self._kind, None
        if kind and self._ops:
            try: self._play(kind, self._opts)
            except Exception: pass                                  # a transition never breaks a screen
        self._ops = []; self._w.refresh()

    # ---- playback
    def _draw(self, ops):
        for y, x, s, attr in ops:
            try: self._w.addstr(y, x, s, attr)
            except Exception: pass

    def _play(self, kind, opts):
        h, w = self._w.getmaxyx(); y_from = opts.get("y_from", FIXED_ROWS)
        still = [o for o in self._ops if o[0] < y_from]; moving = [o for o in self._ops if o[0] >= y_from]
        if not moving: return
        rows = sorted({o[0] for o in moving}); dur = DURATION.get(kind, 0.2); start = time.monotonic()
        while True:
            t = ease((time.monotonic() - start) / dur)
            if t >= 1: break
            frame = []
            if kind == "slide":
                dx = int(round((1 - t) * w * 0.6)) * opts.get("dir", 1)
                for y, x, s, attr in moving:
                    nx, part = _window(s, x + dx, 0, w - 1)
                    if part: frame.append((y, nx, part, attr))
            elif kind == "wipe":
                cut = int(t * (w + 2))
                for y, x, s, attr in moving:
                    nx, part = _window(s, x, 0, min(cut, w - 1))
                    if part: frame.append((y, nx, part, attr))
            else:                                                  # cascade
                shown = set(rows[: max(1, int(round(t * len(rows))))])
                frame = [o for o in moving if o[0] in shown]
            self._w.erase(); self._draw(still); self._draw(frame); self._w.refresh()
            time.sleep(1 / FPS)
        self._w.erase(); self._draw(self._ops)
