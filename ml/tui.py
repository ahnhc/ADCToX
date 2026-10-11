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
        self.s = scr; curses.curs_set(0); scr.keypad(True); self.dim = curses.A_DIM; self.title = curses.A_BOLD; self.cur = curses.A_BOLD
        if curses.has_colors():
            curses.start_color()
            try: curses.use_default_colors(); bg = -1
            except curses.error: bg = curses.COLOR_BLACK
            curses.init_pair(1, curses.COLOR_YELLOW, bg); curses.init_pair(2, curses.COLOR_GREEN, bg)
            self.title = curses.color_pair(1) | curses.A_BOLD; self.cur = curses.color_pair(2) | curses.A_BOLD
    def put(self, y, x, text, attr=0):
        h, w = self.s.getmaxyx()
        if 0 <= y < h - 0 and x < w - 1:
            try: self.s.addstr(y, x, _clip(text, w - x - 1), attr)
            except curses.error: pass
    def header(self, title, description, hint):
        self.s.clear(); y = 1; self.put(y, 2, title, self.title); y += 1
        for line in (description or "").splitlines(): self.put(y, 2, line, self.dim); y += 1
        self.put(y, 2, hint, self.dim); return y + 2

def _enter(k): return k in (10, 13, curses.KEY_ENTER)

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
