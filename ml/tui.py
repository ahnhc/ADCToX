"""Small curses menus (stdlib only): an arrow-key radio list and a searchable checklist.

Modelled on the way `hermes setup` asks questions (hermes_cli/curses_ui.py): full-screen list, yellow title, green cursor row,
" -> (o) item" rows, the default pre-selected, ENTER/SPACE to choose, ESC to fall back to the default, "/" to filter a long list.
Both functions raise nothing on a normal exit and return the chosen index / indices; the caller prints its own summary afterwards.
"""
import locale, os, re, unicodedata
from term import curses
os.environ.setdefault("ESCDELAY", "25")                 # make ESC answer at once instead of waiting for a possible escape sequence
locale.setlocale(locale.LC_ALL, "")
from adc_version import APP_VERSION as UI_VERSION

def _cw(c): return 2 if unicodedata.east_asian_width(c) in "WF" else 1
def _clip(t, n):
    out, w = "", 0
    for c in t:
        if w + _cw(c) > n: break
        out += c; w += _cw(c)
    return out

class _Screen:
    def __init__(self, scr):
        self.s = scr; scr.keypad(True)
        try: curses.curs_set(0)
        except curses.error: pass                       # some consoles cannot hide the cursor
        self.dim = curses.A_DIM; self.title = curses.A_BOLD; self.cur = curses.A_REVERSE
        if curses.has_colors():
            curses.start_color()
            try: curses.use_default_colors(); bg = -1
            except curses.error: bg = curses.COLOR_BLACK
            curses.init_pair(1, curses.COLOR_YELLOW, bg)
            import term
            selected_bg = 236 if term.USE_SHIM or getattr(curses, "COLORS", 0) >= 256 else curses.COLOR_BLUE
            curses.init_pair(2, curses.COLOR_WHITE, selected_bg)
            for n, c in ((3, curses.COLOR_RED), (4, curses.COLOR_YELLOW), (5, curses.COLOR_CYAN), (6, curses.COLOR_GREEN), (7, curses.COLOR_WHITE)):
                curses.init_pair(n, c, bg)
                curses.init_pair(n + 10, c, selected_bg)
            self.title = curses.color_pair(1) | curses.A_BOLD; self.cur = curses.color_pair(2)
    def put(self, y, x, text, attr=0):
        h, w = self.s.getmaxyx()
        if 0 <= y < h - 0 and x < w - 1:
            try: self.s.addstr(y, x, _clip(text, w - x - 1), attr)
            except curses.error: pass
    def put_ansi(self, y, x, text, attr=0, selected=False):
        """text carrying the same ANSI colour codes the printed table uses (31 red, 33 yellow, 36 cyan, 32 green, 90 grey, ;1 bold)."""
        import re
        h, w = self.s.getmaxyx(); col = x; self._ca = self.cur if selected else 0
        for seg in re.split(r"(\x1b\[[\d;]*m)", text):
            if not seg: continue
            m = re.fullmatch(r"\x1b\[([\d;]*)m", seg)
            if m:
                codes = m.group(1).split(";"); a = 0; pair = self.cur if selected else 0
                for c in codes:
                    if c in ("31", "33", "36", "32") and curses.has_colors(): pair = curses.color_pair({"31": 3, "33": 4, "36": 5, "32": 6}[c] + (10 if selected else 0))
                    elif c == "90": a |= curses.A_DIM
                    elif c == "1": a |= curses.A_BOLD
                self._ca = pair | a; continue
            if col >= w - 1: break
            part = _clip(seg, w - 1 - col)
            try: self.s.addstr(y, col, part, attr | getattr(self, "_ca", 0))
            except curses.error: pass
            col += sum(_cw(c) for c in part)
        self._ca = 0

    def rule(self, y):
        _, w = self.s.getmaxyx()
        self.put(y, 2, "─" * max(0, w - 5), self.dim)

    def row(self, y, text, selected=False):
        _, w = self.s.getmaxyx()
        if selected: self.put(y, 2, " " * max(0, w - 5), self.cur)
        self.put_ansi(y, 2, text, selected=selected)

    def brand(self, title=""):
        _, w = self.s.getmaxyx()
        self.put(1, 2, "ADCTOX", self.title)
        self.put(1, max(10, w - 3 - len(UI_VERSION)), UI_VERSION, self.dim)
        self.rule(3)

    def header(self, title, description, hint):
        self.s.erase(); y = 1; self.put(y, 2, title, self.title); y += 1
        for line in (description or "").splitlines(): self.put(y, 2, line, self.dim); y += 1
        self.put(y, 2, hint, self.dim); return y + 2

GLYPH = {"haematologic": "Blood", "hepatic": "Liver", "cardiovascular": "Cardio", "pulmonary": "Lung", "renal": "Kidney",
         "gastrointestinal": "GI", "neurologic": "Neuro", "ocular": "Eye", "dermatologic": "Skin", "metabolic_endocrine": "Metabolic",
         "musculoskeletal": "MSK", "infectious_immune": "Immune", "otologic": "Ear"}     # short organ names of the screens (recommend.ORGAN_SHORT)


LOGO = [                       # drawn by scripts/logo_art.py: A a flask of drug, T a syringe, o a toxic drop, X crossed bones
    ('   ⠙⢻⠛⡟⠋    ⢸⣿⠛⠻⠿⣶⣄⡀   ⢀⣴⠿⠛⠛⠻⢿⡆ ⠛⠛⠛⠛⡟⠛⠛⠛⠃         ⠠⣾⣿⡀    ⢀⣿⣷⠄',
     '   ccccc    cccccccc   cccccccc rrrrrrrrr         rrrr    rrrr'),
    ('    ⣸ ⣇     ⢸⣿    ⠙⣿⣄ ⢰⣿⠃     ⠁   ⢲⠒⠓⢲⡂     ⢀⣶⡀     ⠈⠻⣦⡀⢀⣴⠟⠁  ',
     '    c c     cc    ccc ccc     c   rrrrr     rrr     rrrrrrrr  '),
    ('   ⣼⣁⣀⣈⣧    ⢸⣿     ⢸⣿ ⢸⣿          ⢸⣶⣶⣾⡂    ⢀⡾⣿⣷⡀      ⢈⣿⣿⡁    ',
     '   cyyyc    cc     cc cc          ryyrr    rrrrr      rrrr    '),
    (' ⢠⣾⣿⣽⣿⢿⣿⣷⡄  ⢸⣿    ⣠⣿⠋ ⠸⣿⡄     ⡀   ⢸⣿⣿⣿⠂   ⠠⣿⣼⣿⣿⣿⠄   ⢀⣴⠟⠁⠈⠻⣦⡀  ',
     ' cyyyyyyyc  cc    ccc ccc     c   ryyrr   rrrrrrr   rrrrrrrr  '),
    ('⢰⣿⣿⣿⣿⣽⣿⣿⣿⣿⡆ ⢸⣿⣤⣴⣶⠿⠋⠁   ⠙⢿⣶⣤⣤⣴⡾⠃     ⡇      ⠻⢿⣿⡿⠟  ⠐⢿⣿⠁    ⠈⣿⡿⠂',
     'cyyyyyyyyyc cccccccc   cccccccc     r      rrrrr  rrrr    rrrr'),
]
LOGO_COLOR = {"c": "36", "y": "33", "r": "31"}                  # cyan glass and letters, yellow drug, red toxicity


def logo():
    """the logo as lines of ANSI text: braille cells (2 x 4 dots each, so the dots are square and twice as fine as half
    blocks), one colour per cell."""
    return ["".join(f"\033[{LOGO_COLOR[k]};1m{ch}\033[0m" if k != " " else ch for ch, k in zip(chars, cols)).rstrip() for chars, cols in LOGO]


def logo_width(): return max(len(chars) for chars, _ in LOGO)


def strip(axes, on=(), maybe=()):
    """the organs of a condition as short names in axis order: `on` (linked) green, `maybe` (estimated) yellow with '?';
    none -> a grey dash."""
    parts = [f"\033[32;1m{GLYPH[a]}\033[0m" for a in axes if a in on] + [f"\033[33m{GLYPH[a]}?\033[0m" for a in axes if a in maybe and a not in on]
    return " ".join(parts) if parts else "\033[90m-\033[0m"


def _enter(k): return k in (10, 13, curses.KEY_ENTER)

def _wrap(text, width, indent="    "):
    """wrap by display width (Hangul counts 2), breaking at spaces where possible."""
    width = max(2, width); indent = _clip(indent, max(0, width - 2))
    out, line = [], ""
    for word in text.split(" "):
        cand = (line + " " + word) if line else word
        if sum(_cw(c) for c in cand) <= width: line = cand; continue
        if line: out.append(line); line = indent + word
        else: line = word
        while sum(_cw(c) for c in line) > width:
            cut = _clip(line, width); out.append(cut); line = indent + line[len(cut):]
    if line or not out: out.append(line)
    return out


def _wrap_ansi(text, width):
    """Wrap coloured cells without counting escape sequences as terminal columns."""
    width = max(2, width); out, line, active, used = [], [], "", 0
    for token in re.findall(r"\x1b\[[\d;]*m|[^\x1b]", text):
        if token.startswith("\x1b"):
            active = token; line.append(token); continue
        n = _cw(token)
        if used + n > width:
            spaces = [i for i, value in enumerate(line) if value == " "]
            cut = spaces[-1] + 1 if spaces else 0
            if cut and any(value.strip() and not value.startswith("\x1b") for value in line[:cut]):
                head, tail = line[:cut], line[cut:]
                carry = next((value for value in reversed(head) if value.startswith("\x1b")), "")
                out.append("".join(head) + "\x1b[0m"); line = ([carry] if carry else []) + tail
                used = sum(_cw(value) for value in tail if not value.startswith("\x1b"))
            else:
                out.append("".join(line) + "\x1b[0m"); line = [active] if active else []; used = 0
        line.append(token); used += n
    if line or not out: out.append("".join(line) + ("\x1b[0m" if active else ""))
    return out

def radiolist(title, items, default=0, description=""):
    """items: [(label, detail)]. Returns the chosen index (ESC / q -> default)."""
    def run(scr):
        S = _Screen(scr); cur, top = default, 0
        while True:
            y0 = S.header(title, description, "↑↓ move   ENTER/SPACE choose   ESC default"); h, _ = scr.getmaxyx(); vis = max(1, h - y0 - 1)
            if cur < top: top = cur
            if cur >= top + vis: top = cur - vis + 1
            for k, i in enumerate(range(top, min(len(items), top + vis))):
                label, detail = items[i]; on = i == cur; mark = " (default)" if i == default else ""
                S.put(y0 + k, 0, f" {'→' if on else ' '} ({'●' if on else '○'}) {label}", S.cur if on else 0)
                S.put(y0 + k, 7 + sum(_cw(c) for c in label), f"  {detail}{mark}" if (detail or mark) else "", S.cur if on else S.dim)
            scr.refresh(); key = scr.getch()
            if key in (curses.KEY_UP, ord("k")): cur = max(0, cur - 1)
            elif key in (curses.KEY_DOWN, ord("j")): cur = min(len(items) - 1, cur + 1)
            elif key == curses.KEY_HOME: cur = 0
            elif key == curses.KEY_END: cur = len(items) - 1
            elif key in (curses.KEY_PPAGE,): cur = max(0, cur - vis)
            elif key in (curses.KEY_NPAGE,): cur = min(len(items) - 1, cur + vis)
            elif ord("1") <= key <= ord("9") and key - ord("1") < len(items): cur = key - ord("1")
            elif _enter(key) or key == ord(" "): return cur
            elif key in (27, ord("q")): return default
    return curses.wrapper(run)

def checklist(title, items, checked=(), description="", min_one=True, headers=()):
    """items: [(label, detail)]. SPACE toggles, '/' filters, ENTER confirms. Returns the checked indices, or None on ESC.
    headers: indices of group titles (shown, never selectable; hidden while a search filter is on)."""
    headers = set(headers)
    def run(scr):
        S = _Screen(scr); on = set(checked); cur = top = 0; query = ""; searching = False; note = ""; step = 1
        while True:
            shown = [i for i, (l, d) in enumerate(items) if not query or (i not in headers and query.lower() in (l + " " + d).lower())]
            cur = min(cur, max(0, len(shown) - 1))
            if shown and all(i in headers for i in shown): shown = []
            while shown and shown[cur] in headers:                      # the cursor never rests on a group title
                nxt = cur + step
                if not 0 <= nxt < len(shown): step = -step; nxt = cur + step
                cur = nxt
            hint = f"/{query}_   (ESC clears, ENTER keeps the filter)" if searching else "↑↓ move   SPACE toggle   / search   ENTER confirm   ESC cancel"
            y0 = S.header(title, description, hint); h, _ = scr.getmaxyx(); vis = max(1, h - y0 - 2)
            if cur < top: top = cur
            if cur and shown[cur - 1] in headers and cur - 1 < top: top = cur - 1      # keep a group's title in view
            if cur >= top + vis: top = cur - vis + 1
            for k, p in enumerate(range(top, min(len(shown), top + vis))):
                i = shown[p]; label, detail = items[i]; is_c = p == cur
                if i in headers: S.put(y0 + k, 2, label, S.title); continue
                S.put(y0 + k, 0, f" {'→' if is_c else ' '} [{'x' if i in on else ' '}] {label}", S.cur if is_c else 0)
                S.put(y0 + k, 8 + sum(_cw(c) for c in label), f"  {detail}", S.cur if is_c else 0)
            if not shown: S.put(y0, 2, "(no match)", S.dim)
            S.put(h - 1, 2, f"{len(on)} selected" + (f"   {note}" if note else "") + (f"   filter: {query}" if query and not searching else ""), S.dim)
            scr.refresh(); key = scr.getch(); note = ""
            if searching:
                if key == 27: query, searching = "", False
                elif _enter(key): searching = False
                elif key in (curses.KEY_BACKSPACE, 127, 8): query = query[:-1]
                elif 32 <= key < 127: query += chr(key); cur = top = 0
                elif key == curses.KEY_UP: cur = max(0, cur - 1)
                elif key == curses.KEY_DOWN: cur = min(len(shown) - 1, cur + 1)
                continue
            if key in (curses.KEY_UP, ord("k")): cur = max(0, cur - 1); step = -1
            elif key in (curses.KEY_DOWN, ord("j")): cur = min(len(shown) - 1, cur + 1); step = 1
            elif key == curses.KEY_PPAGE: cur = max(0, cur - vis); step = -1
            elif key == curses.KEY_NPAGE: cur = min(len(shown) - 1, cur + vis); step = 1
            elif key == ord("/"): searching = True; query = ""; cur = top = 0       # a new search starts empty
            elif key == ord(" ") and shown and shown[cur] not in headers: i = shown[cur]; on.symmetric_difference_update({i})
            elif _enter(key):
                if on or not min_one: return sorted(on)
                note = "choose at least one (SPACE)"
            elif key == 27:
                if query: query = ""
                else: return None
    return curses.wrapper(run)


def ranklist(title, items, levels, description=""):
    """items: [(label, detail)], levels: starting level per item (1 = first). UP/DOWN move, LEFT/RIGHT (or -/+) change the
    level of the item under the cursor, the list re-sorts by level and the cursor stays on that item. ENTER confirms,
    ESC returns the starting levels. Equal numbers are equal ranks."""
    def run(scr):
        S = _Screen(scr); lv = list(levels); n = len(items); cur_item = 0
        while True:
            order = sorted(range(n), key=lambda i: (lv[i], i)); cur = order.index(cur_item)
            y0 = S.header(title, description, "↑↓ 이동   ←→ 순위 변경   ENTER 확정   ESC 기본값")
            for k, i in enumerate(order):
                label, detail = items[i]; on = i == cur_item
                S.put(y0 + k, 0, f" {'→' if on else ' '} {lv[i]:>2}   {label}", S.cur if on else 0)
                S.put(y0 + k, 9 + sum(_cw(c) for c in label), f"  {detail}", S.cur if on else S.dim)
            scr.refresh(); key = scr.getch()
            if key in (curses.KEY_UP, ord("k")): cur_item = order[max(0, cur - 1)]
            elif key in (curses.KEY_DOWN, ord("j")): cur_item = order[min(n - 1, cur + 1)]
            elif key in (curses.KEY_LEFT, ord("-"), ord("h")): lv[cur_item] = max(1, lv[cur_item] - 1)
            elif key in (curses.KEY_RIGHT, ord("+"), ord("="), ord("l")): lv[cur_item] = min(n, lv[cur_item] + 1)
            elif _enter(key):
                d = {v: k for k, v in enumerate(sorted(set(lv)), 1)}; return [d[v] for v in lv]      # 1, 3 -> 1, 2
            elif key in (27, ord("q")): return list(levels)
    return curses.wrapper(run)


def browse(title, lines, selectable, details, footer="", context=(), scr=None, crumbs=None):
    """read-only result viewer. lines: the table as text; selectable: indices of lines that are rows; details[k]: text lines
    shown in the bottom panel for selectable row k. UP/DOWN or a mouse click selects a row; PgUp -> "back" (to the input
    steps), PgDn -> "next" (PgUp / PgDn are the only keys that leave a screen). TAB / ENTER switches between the table and scrollable details.
    lines may be a width -> (lines, selectable) renderer; details may be
    a (row, width) -> lines renderer, so the same content reflows when the terminal is resized.
    context may also be a (row, width) -> lines renderer for a bounded input summary.
    scr: draw in this window instead of a new curses session; crumbs(): drawn on the brand line (the step breadcrumb)."""
    def run(scr):
        S = _Screen(scr); cur = 0; top = 0; detail_top = 0; detail_focus = False; last = None
        try: curses.mousemask(curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED | curses.BUTTON1_RELEASED); curses.mouseinterval(0)
        except curses.error: pass
        while True:
            scr.erase(); h, w = scr.getmaxyx()
            import term
            width = max(2, w - 5)
            S.brand(title); y0 = 5
            if crumbs: crumbs()
            header = context(cur, width) if callable(context) else [ln for text in context for ln in _wrap(text, width, "")]
            budget = max(1, h - 20)
            for ln in header[:budget]:
                S.put_ansi(y0, 2, ln); y0 += 1
            if len(header) > budget:
                S.put(y0, 2, f"그 외 {len(header) - budget}줄 · 창을 늘리면 모두 표시", S.dim); y0 += 1
            if context: y0 += 1
            table, choices = lines(width) if callable(lines) else (lines, selectable)
            if not choices: return "next"
            cur = min(cur, len(choices) - 1)
            out = []
            for ln in (details(cur, width) if callable(details) else details[cur]):
                out += _wrap_ansi(ln, width)
            available = max(4, h - y0 - 3)
            panel = min(len(out) + 1, max(3, int(available * (0.75 if detail_focus else 0.55))))
            area = min(len(table), max(1, available - panel))
            sel = choices[cur]
            top = min(top, max(0, len(table) - area))
            if sel < top: top = sel
            if sel >= top + area: top = sel - area + 1
            shown = {}
            for k in range(area):
                i = top + k
                if i >= len(table): break
                end = choices[cur + 1] if cur + 1 < len(choices) else len(table)
                S.row(y0 + k, table[i], sel <= i < end); shown[y0 + k] = i
            yb = y0 + area; S.rule(yb)
            detail_area = max(1, h - yb - 4)
            detail_top = max(0, min(detail_top, len(out) - detail_area))
            for k, ln in enumerate(out[detail_top:detail_top + detail_area]):
                S.put_ansi(yb + 1 + k, 2, ln, curses.A_BOLD if detail_top + k == 0 else 0)
            S.rule(h - 3)
            if detail_focus:
                hint = "↑↓ 이유 스크롤   Tab ADC 목록   PgUp 이전 단계   PgDn 결과 출력"
            else:
                hint = "↑↓ ADC 고르기   Tab 이유 스크롤   PgUp 이전 단계   PgDn 결과 출력"
            if len(out) > detail_area:
                hint += f"   {detail_top + 1}-{min(detail_top + detail_area, len(out))}/{len(out)}"
            S.put(h - 2, 2, hint, S.dim)
            if footer: S.put(h - 1, 2, footer, S.dim)
            if last is not None and cur != last and hasattr(scr, "transition"): scr.transition("cascade", y_from=yb + 1)   # the reasons unfold
            last = cur
            scr.refresh(); key = scr.getch()
            previous = cur
            if key in (curses.KEY_UP, ord("k")):
                if detail_focus: detail_top = max(0, detail_top - 1)
                else: cur = max(0, cur - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                if detail_focus: detail_top = min(max(0, len(out) - detail_area), detail_top + 1)
                else: cur = min(len(choices) - 1, cur + 1)
            elif key in (9, 10, 13, curses.KEY_ENTER): detail_focus = not detail_focus
            elif key == curses.KEY_RIGHT: detail_focus = True
            elif key == curses.KEY_LEFT: detail_focus = False
            elif key == curses.KEY_HOME:
                if detail_focus: detail_top = 0
                else: cur = 0
            elif key == curses.KEY_END:
                if detail_focus: detail_top = max(0, len(out) - detail_area)
                else: cur = len(choices) - 1
            elif key == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, _ = curses.getmouse()
                    if my in shown:
                        hits = [i for i, at in enumerate(choices) if at <= shown[my]]
                        if hits: cur = hits[-1]; detail_focus = False
                except curses.error: pass
            elif key == curses.KEY_PPAGE: return "back"
            elif key == curses.KEY_NPAGE: return "next"
            if cur != previous: detail_top = 0
    return run(scr) if scr is not None else curses.wrapper(run)
