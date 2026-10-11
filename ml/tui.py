"""Small curses menus (stdlib only): an arrow-key radio list and a searchable checklist.

Modelled on the way `hermes setup` asks questions (hermes_cli/curses_ui.py): full-screen list, yellow title, green cursor row,
" -> (o) item" rows, the default pre-selected, ENTER/SPACE to choose, ESC to fall back to the default, "/" to filter a long list.
Both functions raise nothing on a normal exit and return the chosen index / indices; the caller prints its own summary afterwards.
"""
import curses, locale, os, unicodedata
os.environ.setdefault("ESCDELAY", "25")                 # make ESC answer at once instead of waiting for a possible escape sequence
locale.setlocale(locale.LC_ALL, "")

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
        self.dim = curses.A_DIM; self.title = curses.A_BOLD; self.cur = curses.A_BOLD
        if curses.has_colors():
            curses.start_color()
            try: curses.use_default_colors(); bg = -1
            except curses.error: bg = curses.COLOR_BLACK
            curses.init_pair(1, curses.COLOR_YELLOW, bg); curses.init_pair(2, curses.COLOR_GREEN, bg)
            for n, c in ((3, curses.COLOR_RED), (4, curses.COLOR_YELLOW), (5, curses.COLOR_CYAN), (6, curses.COLOR_GREEN), (7, curses.COLOR_WHITE)):
                curses.init_pair(n, c, bg)
            self.title = curses.color_pair(1) | curses.A_BOLD; self.cur = curses.color_pair(2) | curses.A_BOLD
    def put(self, y, x, text, attr=0):
        h, w = self.s.getmaxyx()
        if 0 <= y < h - 0 and x < w - 1:
            try: self.s.addstr(y, x, _clip(text, w - x - 1), attr)
            except curses.error: pass
    def put_ansi(self, y, x, text, attr=0):
        """text carrying the same ANSI colour codes the printed table uses (31 red, 33 yellow, 36 cyan, 32 green, 90 grey, ;1 bold)."""
        import re
        h, w = self.s.getmaxyx(); col = x
        for seg in re.split(r"(\x1b\[[\d;]*m)", text):
            if not seg: continue
            m = re.fullmatch(r"\x1b\[([\d;]*)m", seg)
            if m:
                codes = m.group(1).split(";"); a = 0
                for c in codes:
                    if c in ("31", "33", "36", "32") and curses.has_colors(): a |= curses.color_pair({"31": 3, "33": 4, "36": 5, "32": 6}[c])
                    elif c == "90": a |= curses.A_DIM
                    elif c == "1": a |= curses.A_BOLD
                cur_attr = a; self._ca = a; continue
            if col >= w - 1: break
            part = _clip(seg, w - 1 - col)
            try: self.s.addstr(y, col, part, attr | getattr(self, "_ca", 0))
            except curses.error: pass
            col += sum(_cw(c) for c in part)
        self._ca = 0

    def header(self, title, description, hint):
        self.s.clear(); y = 1; self.put(y, 2, title, self.title); y += 1
        for line in (description or "").splitlines(): self.put(y, 2, line, self.dim); y += 1
        self.put(y, 2, hint, self.dim); return y + 2

def _enter(k): return k in (10, 13, curses.KEY_ENTER)

def _wrap(text, width, indent="    "):
    """wrap by display width (Hangul counts 2), breaking at spaces where possible."""
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


def browse(title, lines, selectable, details, footer=""):
    """read-only result viewer. lines: the table as text; selectable: indices of lines that are rows; details[k]: text lines
    shown in the bottom panel for selectable row k. UP/DOWN or a mouse click selects a row; PgUp -> "back" (to the input
    steps), PgDn / q / ENTER / ESC -> "next"."""
    import textwrap
    def run(scr):
        S = _Screen(scr); cur = 0; top = 0
        try: curses.mousemask(curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED | curses.BUTTON1_RELEASED); curses.mouseinterval(0)
        except curses.error: pass
        while True:
            h, w = scr.getmaxyx(); scr.clear()          # full repaint: the panel height changes with the row
            if title: S.put(0, 1, title, S.title)
            S.put(0, 1, "↑↓ / 클릭   PgUp 이전   PgDn 다음", S.dim)
            out = []
            for ln in details[cur]: out += [ln] if ln[:1] in "┌│├└\x1b" else _wrap(ln, max(20, w - 3))      # table lines are not wrapped
            panel = min(len(out) + 1, max(8, int(h * 0.45))); area = max(3, h - panel - 3); y0 = 2
            sel = selectable[cur]
            if sel < top + 3: top = max(0, sel - 3)
            if sel >= top + area: top = sel - area + 1
            shown = {}
            for k in range(area):
                i = top + k
                if i >= len(lines): break
                S.put_ansi(y0 + k, 0, lines[i], curses.A_REVERSE if i == sel else 0); shown[y0 + k] = i
            yb = y0 + area; S.put(yb, 0, "─" * (w - 1), S.dim)
            for k, ln in enumerate(out[:h - yb - 2]): S.put_ansi(yb + 1 + k, 1, ln, S.title if k == 0 else 0)
            if footer: S.put(h - 1, 1, footer, S.dim)
            scr.refresh(); key = scr.getch()
            if key in (curses.KEY_UP, ord("k")): cur = max(0, cur - 1)
            elif key in (curses.KEY_DOWN, ord("j")): cur = min(len(selectable) - 1, cur + 1)
            elif key == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, _ = curses.getmouse()
                    if my in shown and shown[my] in selectable: cur = selectable.index(shown[my])
                except curses.error: pass
            elif key == curses.KEY_PPAGE: return "back"
            elif key in (ord("q"), 27, 10, 13, curses.KEY_ENTER, curses.KEY_NPAGE): return "next"
    return curses.wrapper(run)
