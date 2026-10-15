"""The few curses calls ml/tui.py and ml/form.py use, drawn with ANSI escape codes, so the menus run where curses is missing
(Windows Python has no curses) or draws Hangul at the wrong width (PDCurses).

    from term import curses       # real curses on Linux / macOS; this stand-in on Windows (or with ADC_TERM_SHIM=1)

The stand-in keeps a cell buffer (a Hangul syllable takes two cells, as terminals draw it), repaints the whole screen on
refresh() in the alternate screen buffer, and reads keys with msvcrt on Windows or a raw tty elsewhere. No mouse.
"""
import os, sys, unicodedata

USE_SHIM = os.name == "nt" or os.environ.get("ADC_TERM_SHIM") == "1"


def windows_console():
    """UTF-8 output and ANSI colours in the Windows console (Windows 10+); harmless elsewhere."""
    if os.name != "nt": return
    try:
        import ctypes
        k = ctypes.windll.kernel32; k.SetConsoleOutputCP(65001); k.SetConsoleCP(65001)
        h = k.GetStdHandle(-11); mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)): k.SetConsoleMode(h, mode.value | 0x0004)      # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception: pass
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass


def into_windows_terminal():
    """started by double-click in the old console (conhost) on Windows: reopen in Windows Terminal if it is installed,
    and end this process. Not when Windows Terminal already runs us (WT_SESSION), with command-line arguments, or --no-wt."""
    import shutil, subprocess
    if os.name != "nt" or os.environ.get("WT_SESSION") or len(sys.argv) > 1 or not sys.stdin.isatty(): return
    wt = shutil.which("wt")
    if not wt: return
    me = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(sys.argv[0])]
    # a PyInstaller one-file exe unpacks itself to a temp folder and deletes it when it exits; a child started with the
    # parent's environment reuses that folder, so it would lose its files when this process ends. Reset tells the child
    # to unpack its own copy.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI"))}; env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    try: subprocess.Popen([wt, "--size", "120,42", "new-tab", "--title", "ADC Recommender", "--", *me], close_fds=True, env=env)
    except OSError: return
    sys.exit(0)


def _cw(c): return 2 if unicodedata.east_asian_width(c) in "WF" else 1


class _Shim:
    error = type("error", (Exception,), {})
    A_NORMAL, A_BOLD, A_DIM, A_REVERSE = 0, 1 << 16, 1 << 17, 1 << 18
    COLOR_BLACK, COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, COLOR_WHITE = range(8)
    KEY_DOWN, KEY_UP, KEY_LEFT, KEY_RIGHT, KEY_HOME, KEY_BACKSPACE = 258, 259, 260, 261, 262, 263
    KEY_NPAGE, KEY_PPAGE, KEY_ENTER, KEY_END, KEY_MOUSE = 338, 339, 343, 360, 409
    BUTTON1_CLICKED = BUTTON1_PRESSED = BUTTON1_RELEASED = 0

    # App-local colours: the alternate buffer is painted explicitly, without changing the user's Terminal profile.
    PALETTE = {0: (23, 24, 21), 1: (237, 150, 144), 2: (154, 193, 145), 3: (226, 184, 114),
               4: (143, 174, 214), 5: (190, 163, 210), 6: (129, 195, 203), 7: (233, 231, 220),
               236: (44, 46, 38), 238: (57, 59, 49), 244: (170, 169, 155)}

    def __init__(self): self._pairs = {}

    # ---- module-level curses functions
    def has_colors(self): return True
    def start_color(self): pass
    def use_default_colors(self): pass
    def init_pair(self, n, fg, bg): self._pairs[n] = (fg, bg)
    def color_pair(self, n): return n << 8
    def curs_set(self, v): sys.stdout.write("\x1b[?25h" if v else "\x1b[?25l"); sys.stdout.flush()
    def mousemask(self, m): raise self.error("no mouse")
    def mouseinterval(self, n): pass
    def getmouse(self): raise self.error("no mouse")

    def wrapper(self, func, *a, **k):
        windows_console(); scr = _Screen(self); out = sys.stdout
        out.write("\x1b[?1049h\x1b[?25l"); out.flush(); scr._raw(True)
        try: return func(scr, *a, **k)
        finally:
            scr._raw(False); out.write("\x1b[0m\x1b[?25h\x1b[?1049l"); out.flush()

    def _sgr(self, attr):
        codes = ["0"]
        if attr & self.A_BOLD: codes.append("1")
        pair = (attr >> 8) & 0xFF
        fg, bg = self._pairs.get(pair, (self.COLOR_WHITE, self.COLOR_BLACK))
        if bg < 0: bg = self.COLOR_BLACK
        if attr & self.A_DIM: fg = 244
        if attr & self.A_REVERSE: bg = 236
        for prefix, value in ((38, fg), (48, bg)):
            if value in self.PALETTE: codes.append(f"{prefix};2;" + ";".join(map(str, self.PALETTE[value])))
            else: codes.append(f"{prefix};5;{value}")
        return "\x1b[" + ";".join(codes) + "m"


class _Screen:
    def __init__(self, C):
        self.C = C; self.h, self.w = self._size(); self.buf = None; self.erase(); self._tty = None

    def _size(self):
        try: s = os.get_terminal_size(); return s.lines, s.columns
        except OSError: return 30, 120

    def keypad(self, flag): pass
    def getmaxyx(self): return self._size()

    def erase(self):
        self.h, self.w = self._size(); self.buf = [[(" ", 0) for _ in range(self.w)] for _ in range(self.h)]
    clear = erase

    def addstr(self, y, x, s, attr=0):
        if not 0 <= y < self.h: return
        row = self.buf[y]
        for ch in s:
            n = _cw(ch)
            if x + n > self.w: break
            row[x] = (ch, attr)
            if n == 2: row[x + 1] = ("", attr)                 # second cell of a wide character
            x += n

    def refresh(self):
        C = self.C; out = ["\x1b[?2026h", "\x1b[H"]; cur = None
        for y, row in enumerate(self.buf):
            out.append(f"\x1b[{y + 1};1H")
            for ch, attr in row:
                if ch == "": continue
                if attr != cur: out.append(C._sgr(attr)); cur = attr
                out.append(ch)
        # Synchronized output keeps the full repaint from flashing in Windows Terminal.
        out.append("\x1b[0m\x1b[?2026l"); sys.stdout.write("".join(out)); sys.stdout.flush()

    # ---- keys
    def _raw(self, on):
        if os.name == "nt" or not sys.stdin.isatty(): return
        import termios, tty
        fd = sys.stdin.fileno()
        if on: self._tty = termios.tcgetattr(fd); tty.setraw(fd)
        elif self._tty: termios.tcsetattr(fd, termios.TCSADRAIN, self._tty)

    def _read(self):
        """-> str (a character) or int (a KEY_ constant)."""
        C = self.C
        if os.name == "nt":
            import msvcrt
            c = msvcrt.getwch()
            if c in ("\x00", "\xe0"):
                return {"H": C.KEY_UP, "P": C.KEY_DOWN, "K": C.KEY_LEFT, "M": C.KEY_RIGHT, "I": C.KEY_PPAGE, "Q": C.KEY_NPAGE,
                        "G": C.KEY_HOME, "O": C.KEY_END}.get(msvcrt.getwch(), -1)
            return c
        import select
        fd = sys.stdin.fileno(); b = os.read(fd, 1)
        if b == b"\x1b":
            seq = b""
            while select.select([fd], [], [], 0.03)[0]:
                seq += os.read(fd, 1)
                if seq[-1:].isalpha() or seq[-1:] == b"~": break
            if not seq: return "\x1b"
            return {b"[A": C.KEY_UP, b"OA": C.KEY_UP, b"[B": C.KEY_DOWN, b"OB": C.KEY_DOWN, b"[C": C.KEY_RIGHT, b"OC": C.KEY_RIGHT,
                    b"[D": C.KEY_LEFT, b"OD": C.KEY_LEFT, b"[5~": C.KEY_PPAGE, b"[6~": C.KEY_NPAGE, b"[H": C.KEY_HOME, b"[F": C.KEY_END}.get(seq, -1)
        n = 1 if b[0] < 0x80 else 2 if b[0] >> 5 == 6 else 3 if b[0] >> 4 == 14 else 4
        while len(b) < n: b += os.read(fd, 1)
        return b.decode("utf-8", "replace")

    def timeout(self, ms):
        """like curses: get_wch waits at most ms milliseconds (negative: forever) and then raises error."""
        self._wait = ms

    def _ready(self):
        ms = getattr(self, "_wait", -1)
        if ms < 0: return True
        import time
        end = time.monotonic() + ms / 1000
        if os.name == "nt":
            import msvcrt
            while not msvcrt.kbhit():
                if time.monotonic() >= end: return False
                time.sleep(0.01)
            return True
        import select
        return bool(select.select([sys.stdin.fileno()], [], [], ms / 1000)[0])

    def get_wch(self):
        if not self._ready(): raise self.C.error("no input")
        k = self._read()
        if k == -1: return self.get_wch()
        return k

    def getch(self):
        k = self.get_wch()
        return ord(k) if isinstance(k, str) else k


if USE_SHIM:
    curses = _Shim()
else:
    import curses  # noqa: F401
