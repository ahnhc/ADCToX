"""One-screen input for ml/recommend.py: each step opens below the finished ones, ESC goes back a step.

Steps: conditions (organ-grouped list; 'Other' at the bottom opens a typing line on the same screen) -> lab values (typed in
place, units as on a lab report) -> [learned estimate for a condition that maps to no organ] -> [priority between conditions].
Returns (conditions, raw lab values) and sets recommend.FALLBACK / recommend.PRIORITY, or None if the user quits.
"""
import re
from term import curses
from tui import _Screen, _cw, _clip, _wrap, _enter, GLYPH, strip, UI_VERSION, logo, logo_width

HANGUL = re.compile("[가-힣]")

BACK, QUIT = "back", "quit"


def marquee(text, width, rest, wait=1.0, speed=5.0, hold=1.2):
    """text that does not fit in width, shifted left once the cursor has rested on it for `wait` seconds: `speed` characters a
    second, a pause of `hold` seconds at the end, then again from the start. Text that fits comes back unchanged."""
    if _w(text) <= width or rest < wait: return text
    over = next(i for i in range(len(text) + 1) if _w(text[i:]) <= width)     # the first start that shows the end
    steps = int((rest - wait) * speed); cycle = over + int(hold * speed) * 2
    start = min(over, max(0, steps % cycle - int(hold * speed)))     # held at the start, moving, held at the end
    return text[start:]
SAVE = __import__("os").path.expanduser("~/.config/adctox/last_input.json")      # entries of the run in progress; deleted once results are shown


def load():
    import json
    try:
        d = json.load(open(SAVE)); return dict(picked=set(d.get("picked", [])), free=d.get("free", ""), raw=d.get("raw", {}), choice=d.get("choice", {}))
    except (OSError, ValueError): return dict(picked=set(), free="", raw={}, choice={})


def clear():
    """forget the entries: called as soon as the result table has been shown."""
    import os
    try: os.remove(SAVE)
    except OSError: pass


def save(st):
    import json, os
    try:
        os.makedirs(os.path.dirname(SAVE), exist_ok=True)
        json.dump(dict(picked=sorted(st["picked"]), free=st["free"], raw=st["raw"], choice=st.get("choice", {})), open(SAVE, "w"), ensure_ascii=False)
    except OSError: pass


def _w(s): return sum(_cw(c) for c in s)


def _key(scr, tab=False):
    try: k = scr.get_wch()
    except curses.error: return None
    if isinstance(k, str):
        if k in ("\n", "\r"): return "ENTER"
        if k == "\x1b": return "ESC"
        if k in ("\x7f", "\x08"): return "BS"
        if k == "\t": return "TAB" if tab else "DOWN"
        return k
    if k == curses.KEY_MOUSE:                                     # a click -> ("CLICK", y, x); the wheel scrolls like the arrows
        try: _, x, y, _, b = curses.getmouse()
        except curses.error: return None
        if b & getattr(curses, "BUTTON4_PRESSED", 0): return "UP"
        if b & getattr(curses, "BUTTON5_PRESSED", 0): return "DOWN"
        if b & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | getattr(curses, "BUTTON1_RELEASED", 0)): return ("CLICK", y, x)
        return None
    return {curses.KEY_UP: "UP", curses.KEY_DOWN: "DOWN", curses.KEY_BACKSPACE: "BS", curses.KEY_ENTER: "ENTER",
            curses.KEY_LEFT: "LEFT", curses.KEY_RIGHT: "RIGHT", curses.KEY_PPAGE: "PGUP", curses.KEY_NPAGE: "PGDN"}.get(k)


def split_free(text):
    """'copd ,   asthma,heart  stop' -> ['copd', 'asthma', 'heart stop']"""
    return [" ".join(x.split()) for x in text.split(",") if x.strip()]


class _ProcessUsage:
    """Actual CPU time and resident RAM for this process, including its model runtime."""
    def __init__(self):
        import time
        self.wall, self.cpu = time.monotonic(), time.process_time()
        self.percent = 0.0

    def line(self):
        import os, time
        wall, cpu = time.monotonic(), time.process_time()
        if wall - self.wall >= 0.2:
            self.percent = max(0.0, 100 * (cpu - self.cpu) / (wall - self.wall))
            self.wall, self.cpu = wall, cpu
        try:
            with open("/proc/self/statm") as stream:
                resident = int(stream.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
            ram = f"{resident / 1024**3:.2f} GiB"
        except (OSError, ValueError, IndexError, AttributeError):
            try:                                                      # macOS: peak resident size, in bytes there
                import resource, sys
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
                ram = f"{peak / 1024**3:.2f} GiB (peak)"
            except (ImportError, OSError, ValueError): ram = "unavailable"
        return f"CPU {self.percent:.1f}%   RAM {ram}"


APP_CHECK = {}                              # the published app version, read once a day in the background (installed apps only)


def _check_app():
    try:
        import adc_updates
        if adc_updates.app_layout() is not None: APP_CHECK.update(adc_updates.check_app() or {})
    except Exception:
        pass


class Form:
    def __init__(self, scr, RC):
        if not APP_CHECK and getattr(RC, "HAS_LEARNED", False): APP_CHECK["started"] = True; __import__("threading").Thread(target=_check_app, daemon=True).start()
        self.S, self.scr, self.RC = _Screen(scr), scr, RC
        self.done = []                      # [(step title, summary)] shown above the current step
        self.usage = _ProcessUsage()
        self.analysis_cached = False
        self.hits = []                      # [(y, x0, x1, value)] clickable places of the current frame
        try:
            curses.mousemask(curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | getattr(curses, "BUTTON4_PRESSED", 0) | getattr(curses, "BUTTON5_PRESSED", 0))
            curses.mouseinterval(0)
        except curses.error: pass

    def hit(self, y, x0, x1, value):
        self.hits.append((y, x0, x1, value))

    def row(self, y, text, on, value):
        """a selectable row; a click on it returns ("ROW", value) from key()."""
        self.S.row(y, text, on); self.hit(y, 0, 10 ** 4, ("ROW", value))

    def button(self, y, x, label, value, on=False):
        """[ label ] drawn at (y, x), clickable; -> its width."""
        t = f"[ {label} ]"; self.S.put(y, x, t, self.S.cur if on else self.S.title); self.hit(y, x, x + _w(t), value); return _w(t)

    def timeout(self, ms):
        self._to = ms; self.scr.timeout(ms)

    def _escape(self):
        """after ESC: the rest of an escape sequence curses did not translate (a mouse report in a format the terminal chose).
        -> ("CLICK", y, x), "UP" / "DOWN" for the wheel, "NOOP" for other sequences, or "ESC" when ESC was pressed alone."""
        import re
        self.scr.timeout(30); seq = ""
        try:
            while len(seq) < 24:
                try: c = self.scr.get_wch()
                except curses.error: break
                if not isinstance(c, str): break
                seq += c
                if seq[-1:].isalpha() or seq[-1:] == "~": break
        finally:
            self.scr.timeout(getattr(self, "_to", -1))
        if not seq: return "ESC"
        m = re.fullmatch(r"\[<(\d+);(\d+);(\d+)([Mm])", seq)
        if m:
            b = int(m.group(1))
            if b == 64: return "UP"
            if b == 65: return "DOWN"
            return ("CLICK", int(m.group(3)) - 1, int(m.group(2)) - 1) if b & 3 == 0 and not b & 32 and m.group(4) == "M" else "NOOP"
        return {"[A": "UP", "[B": "DOWN", "[5~": "PGUP", "[6~": "PGDN", "[C": "RIGHT", "[D": "LEFT"}.get(seq, "NOOP")

    def key(self, tab=False):
        """the next key, with a click turned into what it pressed: a key name ("PGDN", "TAB" ...) or ("ROW", value)."""
        k = _key(self.scr, tab)
        if k == "ESC": k = self._escape()
        if isinstance(k, tuple) and k[0] == "CLICK":
            _, y, x = k
            for hy, x0, x1, v in reversed(self.hits):
                if hy == y and x0 <= x < x1: return v
            return "NOOP"
        return k

    def frame(self, title, hint, nav=("PGUP", "PGDN")):
        """draw the finished steps and the current step's title, with clickable ◀ 이전 / 다음 ▶ at the top right; -> first free row."""
        self.scr.erase(); h, w = self.scr.getmaxyx(); y = 5; self.hits = []
        self.S.brand()
        bx = w - 3
        for label, value in reversed([(l, v) for l, v in (("◀ 이전", "PGUP"), ("다음 ▶", "PGDN")) if v in nav]):
            bx -= _w(f"[ {label} ]") + 1; self.button(2, bx, label, value)
        nav_hint = "   ".join(t for t, v in (("PgUp ◀ 이전", "PGUP"), ("PgDn 다음 ▶", "PGDN")) if v in nav)
        self.S.put(h - 1, max(1, w - 2 - _w(nav_hint)), nav_hint, self.S.dim)
        for t, s in self.done:
            for k, ln in enumerate(_wrap(f"✓ {t}: {s}", w - 5, "    ")[:2]): self.S.put(y, 2, ln, self.S.dim); y += 1
        if self.done: y += 1
        for ln in _wrap(title, w - 5, ""):
            self.S.put(y, 2, ln, self.S.title); y += 1
        if hint:
            for ln in _wrap(hint, w - 5, ""):
                self.S.put(y, 2, ln, self.S.dim); y += 1
        return y + 1

    # ------------------------------------------------------------------ step 1
    def conditions(self, picked, free, choice=None):
        """disease input in one box: names are suggested while typing; a sentence or symptoms (two or more words) also gets
        diseases found from the symptoms after a short pause. -> (registry ids, free text 'a, b', {free text: MONDO id}) or QUIT."""
        import threading, time, suggest as SG
        RC = self.RC; choice = dict(choice or {})
        sel = [("reg", i, RC.condition_name(i), RC._reg[i]["organ_axes"].split(";")) for i in RC._reg if i in picked]
        sel += [("mondo" if f in choice else "text", choice.get(f, f), f, []) for f in split_free(free)]
        query, cur, note = "", 0, ""
        found, ai, sym = [], dict(q=None, res=[], busy=False), dict(q=None, res=None, busy=False, error="")
        typed_at = 0.0; ai_on = RC.HAS_LEARNED; dirty = False; searched_at = 0.0
        def search():                                              # spelling suggestions; during fast typing at most every 0.15 s
            nonlocal found, dirty, searched_at
            found = SG.names(RC, query); dirty = False; searched_at = time.monotonic()
        threading.Thread(target=SG.index(RC).load_mondo, daemon=True).start()       # MONDO and KCD names, about 2 s
        sentence = lambda q: len(q) >= 4 and len(q.split()) >= 2 and not SG.parts(RC, q)     # symptoms or a sentence, not 'asd adhd'

        def run_ai(q):
            try: res = SG.semantic(RC, q)
            except Exception: res = []
            if ai["q"] == q: ai["res"] = res
            ai["busy"] = False

        def run_sym(q):
            try: res = SG.symptoms(RC, q, semantic=RC.HAS_LEARNED); err = ""
            except Exception as e: res, err = [], f"{type(e).__name__}: {str(e)[:80]}"
            if sym["q"] == q: sym["res"], sym["error"] = res, err
            sym["busy"] = False

        def add(s):
            kind, val, label, detail, org = s[:5]
            if kind in ("mondo", "reg"): label = names_of("s", s)[0]      # the name as it was shown (the typed language); a registry pick is kept by id
            if any((x[0], x[1]) == (kind, val) or x[2].lower() == label.lower() for x in sel): return f"이미 선택됨: {label}"
            sel.append((kind, val, label, org)); return f"추가: {label}"

        I = SG.index(RC)
        def names_of(kind, s):                                     # (main name, second name): Korean first only when Korean was typed
            if kind == "sel": return s[2], ""
            a, b = s[2], (s[3] if kind in ("s", "sym") and s[3] and s[3] != s[2] else "")
            ko_typed = bool(HANGUL.search(query))
            if b and bool(HANGUL.search(b)) == ko_typed and bool(HANGUL.search(a)) != ko_typed: a, b = b, a
            return a, b

        def keys(x):                                               # what makes two rows the same disease: id, MONDO id, either name
            mondo = RC._reg[x[1]].get("mondo_id") if x[0] in ("reg", "sel") and x[1] in RC._reg else x[1] if str(x[1]).startswith("MONDO:") else None
            k = {(x[0] if x[0] != "sel" else "reg", str(x[1])), ("name", re.sub(r"\W", "", str(x[2]).lower()))}
            if mondo: k.add(("mondo", mondo))
            if len(x) > 3 and x[3] and HANGUL.search(str(x[3])): k.add(("name", re.sub(r"\W", "", str(x[3]))))
            return k
        def fresh(x, have):
            k = keys(x)
            if k & have: return False
            have |= k; return True

        self.timeout(100)
        rested = [None, 0.0]                                       # (row, query) under the cursor and since when, for the scrolling name
        try:
            while True:
                q = query.strip()
                have = set().union(*[keys(x) for x in sel]) if sel else set()       # a disease once: picked, or in any section
                rows = [("s", x, "") for x in found if fresh(x, have)]
                if ai["q"] == q and ai["res"]:
                    rows += [("s", x, "AI") for x in ai["res"] if fresh(x, have)]
                split = SG.parts(RC, query)
                if split: rows.insert(0, ("split", ("text", split, "각각 따로 추가: " + ", ".join(split), "", []), ""))
                if sym["q"] == q and sym["res"]:
                    rows += [("sym", x, why) for x, why in sym["res"] if fresh(x, have)]
                if q: rows.append(("raw", ("text", q, q, "", []), ""))       # last: Enter first takes the best suggestion
                cur = max(0, min(cur, len(rows) - 1))
                # ---- a search page: title, the picked diseases as chips, one box, suggestions under it
                self.scr.erase(); self.hits = []; h, w = self.scr.getmaxyx()
                bw = max(20, min(w - 6, 66)); bx = (w - bw) // 2
                self.S.put(0, max(2, w - 2 - len(UI_VERSION)), UI_VERSION, self.S.dim)
                if sel: self.button(1, max(2, w - 3 - _w("[ 다음 ▶ ]")), "다음 ▶", "PGDN")
                big = w >= logo_width() + 4 and h >= 20
                block = (5 if big else 1) + 2 + 2
                y = 2 if (rows or sel) else max(1, (h - block) // 2 - 1)
                if big:
                    for ln in logo(): self.S.put_ansi(y, (w - logo_width()) // 2, ln); y += 1
                else: self.S.put_ansi(y, (w - 6) // 2, "\033[36;1mADC\033[0m\033[31;1mToX\033[0m"); y += 1
                y += 2
                if sel:                                                    # chips; a click or Backspace on an empty box takes one off
                    x = bx
                    for n, item in enumerate(sel):
                        ax = item[3] or (I.organs.get(item[1], []) if item[0] == "mondo" else [])
                        org = ", ".join(GLYPH[a] for a in RC.AXES if a in ax)
                        chip = f"[ {item[2]}" + (f"  {org}" if org else "") + " × ]"
                        if x + _w(chip) > bx + bw and x > bx: y += 1; x = bx
                        self.S.put_ansi(y, x, f"\033[32;1m[\033[0m {_clip(item[2], bw - 12)}" + (f"  \033[90m{org}\033[0m" if org else "") + " \033[31m×\033[0m \033[32;1m]\033[0m")
                        self.hit(y, x, x + _w(chip), ("CHIP", n)); x += _w(chip) + 2
                    y += 1
                if query: self.S.put(y, bx + 1, "› " + _clip(query, bw - 6)[-(bw - 6):] + "_", self.S.title)    # the box: one line and an underline
                else: self.S.put(y, bx + 1, "› " + _clip("질환명이나 증상을 입력하세요", bw - 5), self.S.dim)
                self.S.put(y + 1, bx, "─" * bw, self.S.dim); y += 2
                status = ""
                if ai["busy"]: status = "AI 추천 찾는 중 ..."
                if sym["busy"]: status = "증상으로 질환 찾는 중 ...   처음 한 번은 모델을 불러 10초쯤 걸립니다"
                if sym["error"]: status = "증상 검색 실패: " + sym["error"]
                lw = min(max([_w(names_of(r[0], r[1])[0]) for r in rows if r[0] in ("s", "sym")] + [10]), max(16, bw // 2 + 2))
                orgs = {}
                for k, (kind, s, tag) in enumerate(rows):
                    if kind in ("s", "sym"):
                        orgs[k] = strip(RC.AXES, s[4]) if s[4] else "\033[90m" + ("none of 13" if s[0] in ("mondo", "reg") and (I.mondo_loaded or s[0] == "reg") else "분석 때 판정") + "\033[0m"
                ow = min(max([_w(re.sub(r"\x1b\[[\d;]*m", "", o)) for o in orgs.values()] + [6]), 16)
                lines = []; tip = ""
                for k, (kind, s, tag) in enumerate(rows):
                    if kind == "sym" and not any(l[0] == "head" for l in lines): lines += [("head", ""), ("head", "증상·문장으로 찾은 질환")] if k else [("head", "증상·문장으로 찾은 질환")]
                    lines.append((k, kind, s, tag))
                area = max(3, h - y - 3)
                at = next((i for i, l in enumerate(lines) if l[0] == cur), 0)
                top = max(0, min(at - area // 2, len(lines) - area))
                for r, l in enumerate(lines[top:top + area]):
                    yy = y + r
                    if l[0] == "head": self.S.put(yy, bx + 2, l[1], self.S.dim); continue
                    k, kind, s, tag = l; on = k == cur
                    if kind == "raw": text = f"\033[90m+ 입력한 그대로 추가:\033[0m {s[2]}"
                    elif kind == "split": text = s[2]
                    else:
                        main, sub = names_of(kind, s); org = orgs[k]
                        label = _clip(marquee(main, lw, time.monotonic() - rested[1]) if on else main, lw)
                        plain = re.sub(r"\x1b\[[\d;]*m", "", org)
                        room = max(0, bw - 10 - lw - ow); tail = tag if kind == "sym" else sub
                        if on and kind != "sym" and sub and (_w(sub) > room or _w(main) > lw): tip = f"{main}  ·  {sub}"     # the whole names, under the list
                        tail = tail if _w(tail) <= room else (_clip(tail, room) if kind == "sym" else "")   # a second name is shown whole or not at all
                        text = f"{label}{' ' * (lw - _w(label))}   {org}{' ' * max(0, ow - _w(plain))}   \033[90m{tail}\033[0m" + (f" \033[90m{tag}\033[0m" if tag == "AI" else "")
                    if on: self.S.put(yy, bx, " " * bw, self.S.cur)
                    self.S.put_ansi(yy, bx + 1, f"{'→' if on else ' '} {text}", selected=on); self.hit(yy, bx, bx + bw, ("ROW", k))
                foot = "Enter 추가   ↑↓ 선택   " + ("× 또는 Backspace 빼기   PgDn 다음" if sel else "Esc 종료")
                if APP_CHECK.get("newer"): foot += f"   새 앱 {APP_CHECK['latest']}: adctox --update-app"
                for yy, t in ((h - 4, tip), (h - 3, note), (h - 2, status), (h - 1, foot)):
                    if t: self.S.put(yy, max(1, (w - _w(t)) // 2), _clip(t, w - 2), self.S.dim)
                if rested[0] != (cur, q): rested[:] = [(cur, q), time.monotonic()]
                self.scr.refresh(); k = self.key(tab=True)
                if isinstance(k, tuple) and k[0] == "ROW": cur = k[1]; k = "ENTER"     # a click on a row picks it
                if isinstance(k, tuple) and k[0] == "CHIP":
                    if k[1] < len(sel): note = f"뺌: {sel.pop(k[1])[2]}"
                    continue
                if k in ("NOOP", "TAB"): continue
                if k is None:                                              # no key within 0.1 s: searches that wait for a pause
                    if dirty: search()
                    idle = time.monotonic() - typed_at
                    if ai_on and len(q) >= 2 and ai["q"] != q and not ai["busy"] and idle > 0.35 and not sentence(q):
                        ai.update(q=q, res=[], busy=True); threading.Thread(target=run_ai, args=(q,), daemon=True).start()
                    if sentence(q) and sym["q"] != q and not sym["busy"] and idle > 0.6:
                        sym.update(q=q, res=None, busy=True, error=""); threading.Thread(target=run_sym, args=(q,), daemon=True).start()
                    continue
                note = ""
                if k == "UP": cur = max(0, cur - 1)
                elif k == "DOWN": cur = min(len(rows) - 1, cur + 1)
                elif k == "PGDN":
                    if sel: return self._split(sel)
                    note = "질환을 하나 이상 추가하세요"
                elif k == "ESC":
                    if query: query, found, cur = "", [], 0
                    else: return QUIT
                elif k == "ENTER":
                    if not rows: note = "질환명이나 증상을 입력하세요" if not sel else "다음 단계는 다음 ▶ 또는 PgDn"; continue
                    kind, s, _ = rows[cur]
                    if kind == "split":
                        note = "   ".join(add(("text", w_, w_, "", [])) for w_ in s[1]); query, found, cur = "", [], 0
                    else:
                        note = add(s); query, found, cur = "", [], 0
                elif k == "BS" and not query:
                    if sel: note = f"뺌: {sel.pop()[2]}"
                elif k == "BS" or (isinstance(k, str) and len(k) == 1 and k.isprintable()):
                    query = query[:-1] if k == "BS" else query + k; typed_at = time.monotonic(); cur = 0; dirty = True
                    if not query or time.monotonic() - searched_at > 0.15: search()
        finally:
            self.timeout(-1)

    def _split(self, sel):
        picked = {x[1] for x in sel if x[0] == "reg"}
        free = [x[2] for x in sel if x[0] != "reg"]
        choice = {x[2]: x[1] for x in sel if x[0] == "mondo"}
        return picked, ", ".join(free), choice

    def labs(self, raw):
        import labs as LB
        fields = LB.FIELDS; show = lambda v: ("y" if v else "n") if isinstance(v, bool) else (f"{v:g}" if isinstance(v, float) else str(v))
        vals = {k: "" if raw.get(k) is None else show(raw[k]) for k, *_ in fields}
        rows = []                                                      # ("head", group) / ("field", index) / ("done",)
        g = None
        for i, (k, label, unit, grp) in enumerate(fields):
            if grp != g: rows.append(("head", grp)); g = grp
            rows.append(("field", i))
        pick = [r for r, x in enumerate(rows) if x[0] != "head"]; cur = 0; note = ""
        lw = max(len(l) for _, l, _, _ in fields)
        while True:
            at = pick[cur]
            y0 = self.frame("검사 수치", "아는 것만 입력하세요")
            h, w = self.scr.getmaxyx(); area = max(3, h - y0 - 2); top = max(0, min(at - area // 2, len(rows) - area))
            for r, x in enumerate(rows[top:top + area]):
                row = top + r; on = row == at
                if x[0] == "head": self.S.put(y0 + r, 2, x[1], self.S.title)
                elif x[0] == "done": self.row(y0 + r, f" {'→' if on else ' '} [ 완료 ]", on, row)
                else:
                    k, label, unit, _ = fields[x[1]]; v = vals[k]
                    self.row(y0 + r, f" {'→' if on else ' '} {label:<{lw}}  {v + ('_' if on else ''):<10} {unit}", on, row)
            parsed = {}
            for key, v in vals.items():                                 # a value still being typed ("0", "0.") is just left out
                try:
                    if v.strip(): parsed[key] = LB.parse(key, v)
                except ValueError: pass
            try: info = "   ".join(n for n in LB.derive(parsed)[2] if n.startswith("CLcr"))
            except Exception: info = ""
            self.S.put(h - 1, 1, note or info, self.S.dim); note = ""
            self.scr.refresh(); k = self.key()
            if isinstance(k, tuple):                                       # a click moves to the field (or finishes on 완료)
                cur = pick.index(k[1]) if k[1] in pick else cur; at = pick[cur]; k = "NOOP"
            x = rows[at]
            if k == "UP": cur = max(0, cur - 1)
            elif k == "DOWN": cur = min(len(pick) - 1, cur + 1)
            elif k == "PGUP": return BACK
            elif k == "ESC" and x[0] == "field": vals[fields[x[1]][0]] = ""
            elif k == "ENTER" or k == "PGDN":
                if k == "PGDN":
                    out = {}
                    for key, v in vals.items():
                        if not v.strip(): continue
                        try: out[key] = LB.parse(key, v)
                        except ValueError as e: note = f"{key}: {e}"; break
                    else: return out
                else:
                    key = fields[x[1]][0]
                    try: LB.parse(key, vals[key]); cur = min(len(pick) - 1, cur + 1)
                    except ValueError as e: note = f"{fields[x[1]][1]}: {e}"
            elif x[0] == "field":
                key = fields[x[1]][0]
                if k == "BS": vals[key] = vals[key][:-1]
                elif isinstance(k, str) and len(k) == 1 and k.isprintable() and len(vals[key]) < 10: vals[key] += k

    # ------------------------------------------------------------------ generic choice / order
    def choose(self, title, desc, options, default=0):
        cur = default
        while True:
            y0 = self.frame(title, "")
            h, w = self.scr.getmaxyx()
            for paragraph in desc.splitlines() if desc else []:
                if "\033[" in paragraph: self.S.put_ansi(y0, 2, paragraph); y0 += 1; continue          # a drawn line (organ strip)
                for ln in _wrap(paragraph, w - 5, "    "): self.S.put(y0, 2, ln, self.S.dim); y0 += 1
            if desc: y0 += 1
            for i, o in enumerate(options): self.row(y0 + i, f" {'→' if i == cur else ' '} ({'●' if i == cur else '○'}) {o}", i == cur, i)
            self.scr.refresh(); k = self.key()
            if isinstance(k, tuple): cur = k[1]; continue                  # a click picks; PgDn goes on
            if k == "UP": cur = max(0, cur - 1)
            elif k == "DOWN": cur = min(len(options) - 1, cur + 1)
            elif k == "PGDN": return cur
            elif k == "PGUP": return BACK

    def meanings(self, groups, chosen):
        """one screen for every typed text that reads as several diseases. groups: [(text, readings)]; chosen: {text: id or None}.
        -> {text: id or None (unknown)} or BACK."""
        RC = self.RC; pick = {}; rows = []                      # ("head", text) / ("opt", text, id, label, organs, tag)
        for g, (text, opts) in enumerate(groups):
            if g: rows.append(("gap",))
            rows.append(("head", text))
            for r in opts:
                name = r["name"][:1].upper() + r["name"][1:]
                rows.append(("opt", text, r["mondo"], name, strip(RC.AXES, r["organs"]) if r["organs"] else "\033[90m13개 장기 밖\033[0m", "증상" if str(r["mondo"]).startswith("HP:") else ""))
            rows.append(("opt", text, None, "모름", "", ""))
            ids = [r["mondo"] for r in opts]; pick[text] = chosen.get(text, ids[0]) if chosen.get(text, ids[0]) in ids + [None] else ids[0]
        sel = [i for i, x in enumerate(rows) if x[0] == "opt"]; cur = 0
        nw = max(_w(x[3]) + (_w(x[5]) + 3 if x[5] else 0) for x in rows if x[0] == "opt")
        while True:
            y0 = self.frame("입력하신 질환 확인", "")
            h, w = self.scr.getmaxyx()
            self.S.put(y0, 2, "여러 질환으로 읽히는 입력이 있습니다. 의도한 질환을 골라 주세요.", self.S.dim); y0 += 2
            at = sel[cur]; area = max(3, h - y0 - 1); top = max(0, min(at - area // 2, len(rows) - area))
            for r, x in enumerate(rows[top:top + area]):
                y = y0 + r
                if x[0] == "gap": continue
                if x[0] == "head":
                    self.S.put(y, 2, x[1], self.S.title); continue
                on = top + r == at; mark = "●" if pick[x[1]] == x[2] else "○"
                name = x[3] + (f"   {x[5]}" if x[5] else "")
                self.row(y, f" {'→' if on else ' '}  {mark}  {name}{' ' * (nw - _w(name))}   {x[4]}", on, top + r)
            self.scr.refresh(); k = self.key()
            if isinstance(k, tuple):
                if k[1] in sel: cur = sel.index(k[1]); at = sel[cur]; k = " "
                else: continue
            if k == "UP": cur = max(0, cur - 1)
            elif k == "DOWN": cur = min(len(sel) - 1, cur + 1)
            elif k in ("ENTER", " "):
                x = rows[at]; pick[x[1]] = x[2]
                nxt = [j for j, i in enumerate(sel) if i > at and rows[i][1] != x[1]]   # jump to the next question's current pick, or finish
                if nxt: g = rows[sel[nxt[0]]][1]; cur = next((j for j in nxt if rows[sel[j]][1] == g and rows[sel[j]][2] == pick[g]), nxt[0])
            elif k == "PGDN": return pick
            elif k == "PGUP": return BACK

    def order(self, names, details, levels, organs=None):
        """priority between conditions: 1 = avoid its organs' toxicity first. ←→ or the clickable − / + change a level."""
        lv = list(levels); n = len(names); it = 0
        while True:
            y0 = self.frame("어느 질환 쪽 독성을 먼저 피할까요?", "1 = 먼저 피함 · 같은 숫자 = 같은 순위 · ←→ 또는 − + 클릭")
            order = sorted(range(n), key=lambda i: (lv[i], i)); pos = order.index(it); w0 = max(_w(x) for x in names)
            for r, i in enumerate(order):
                on = i == it; y = y0 + r * 2
                pic = strip(self.RC.AXES, organs[i]) if organs else details[i]
                self.row(y, f" {'→' if on else ' '}     {lv[i]:>2}       {names[i]}{' ' * (w0 - _w(names[i]))}   {pic}", on, i)
                self.button(y, 5, "−", ("DEC", i)); self.button(y, 13, "+", ("INC", i))
            self.scr.refresh(); k = self.key()
            if isinstance(k, tuple):
                kind, i = k[0], k[1]; it = i
                if kind == "DEC": lv[i] = max(1, lv[i] - 1)
                elif kind == "INC": lv[i] = min(n, lv[i] + 1)
                continue
            if k == "UP": it = order[max(0, pos - 1)]
            elif k == "DOWN": it = order[min(n - 1, pos + 1)]
            elif k in ("LEFT", "-"): lv[it] = max(1, lv[it] - 1)
            elif k in ("RIGHT", "+", "="): lv[it] = min(n, lv[it] + 1)
            elif k == "PGDN": d = {v: j for j, v in enumerate(sorted(set(lv)), 1)}; return [d[v] for v in lv]
            elif k == "PGUP": return BACK

    def loading(self, text):
        y0 = self.frame(text, ""); self.scr.refresh()

    def analyze(self, conditions):
        """Keep curses on the main thread; animate only stages the actual model reports."""
        import queue, threading, time
        events = queue.SimpleQueue(); result = []; errors = []
        free = [c for c in conditions if c not in self.RC._reg and c.lower() not in self.RC._by_label and c not in self.RC.CONTEXT]
        self.analysis_cached = tuple(free) in self.RC._FREE and (not self.RC.HAS_LEARNED or all(c in self.RC._FREE_PREDICTIONS for c in free))
        self.usage = _ProcessUsage()
        def work():
            try: result.extend(self.RC.analyze_conditions(conditions, progress=events.put))
            except Exception as error: errors.append(error)
        stages = [("embedding", "Disease embedding", "BioLORD-2023"),
                  ("linking", "Disease linking", "SapBERT / MONDO"),
                  ("judging", "Organ judgment", "Gemma 4 E2B (int8)"),
                  ("inference", "Organ inference", "Disease-pair MLP")]
        current = 0; started = time.monotonic()
        worker = threading.Thread(target=work, daemon=True); worker.start()
        timeout = getattr(self.scr, "timeout", None)
        if timeout: timeout(100)
        try:
            while worker.is_alive():
                while not events.empty():
                    event = events.get()
                    current = next((i for i, (key, _, _) in enumerate(stages) if key == event), len(stages))
                y = self.frame("AI 장기 분석", "직접 입력한 질환의 관련 장기를 분석하고 있습니다")
                _, w = self.scr.getmaxyx()
                names = ", ".join(c for c in conditions if c not in self.RC._reg and c.lower() not in self.RC._by_label and c not in self.RC.CONTEXT)
                for ln in _wrap(names, w - 5, "  ")[:2]: self.S.put(y, 2, ln); y += 1
                y += 1
                for i, (_, name, model) in enumerate(stages):
                    marker = "[OK]" if i < current else ("[" + "|/-\\"[int((time.monotonic()-started)*8) % 4] + " ]" if i == current else "[  ]")
                    tone = "32" if i < current else "33;1" if i == current else "90"
                    self.S.put_ansi(y, 2, f"\033[{tone}m{marker} {name:<20} {model}\033[0m"); y += 2
                self.S.put(y + 1, 2, f"Running   {time.monotonic()-started:.1f} s", self.S.dim)
                h, _ = self.scr.getmaxyx()
                self.S.put(h - 2, 2, "AI process   " + self.usage.line(), self.S.dim)
                self.scr.refresh()
                if timeout: _key(self.scr)
                else: time.sleep(0.1)
        finally:
            if timeout: timeout(-1)
        worker.join()
        if errors:
            self.choose("AI 분석을 완료하지 못했습니다", f"모델 실행 환경을 확인해 주세요.\n{type(errors[0]).__name__}: {str(errors[0])[:160]}", ["질환 입력으로 돌아가기"])
            return BACK
        return result, time.monotonic() - started

    def analysis_review(self, reports, elapsed):
        timeout = getattr(self.scr, "timeout", None)
        if timeout: timeout(500)
        try: return self._analysis_review(reports, elapsed)
        finally:
            if timeout: timeout(-1)

    def _analysis_review(self, reports, elapsed):
        """per typed condition: what it was read as and its organs (the ones the recommendation uses), one line each; under it, for
        the highlighted input, what each Gemma judge output said and which step set the organs."""
        import tui, suggest as SG
        top = cur = 0; RC = self.RC; ko = SG.index(RC).ko
        SOURCE = {"AI judgment": "AI judgment (Gemma)", "Registry match": "Registry", "Similar condition": "Similar registry condition",
                  "Phenotype (HPO)": "HPO phenotype", "Chosen": "Chosen", "Unmapped": "Not understood"}
        while True:
            y0 = self.frame("AI 장기 분석", "")
            h, w = self.scr.getmaxyx(); width = max(2, w - 5)
            nw = min(24, max(_w(r["condition"]) for r in reports))
            rows = []
            for r in reports:
                picked = RC.CHOICE.get(r["condition"]) or ""
                kr = bool(HANGUL.search(r["condition"]))           # the disease name in the language of the input
                read = ((ko.get(r.get("mondo") or "") if kr else "") or r["name"]) if r["source"].startswith("MONDO") else ((ko.get(picked) if kr else "") or r["name"] or "")
                how = "MONDO" if r["source"].startswith("MONDO") else SOURCE.get(r["source"], r["source"])
                org = strip(RC.AXES, r["organs"]) if r["organs"] else "\033[90m" + ("none of 13" if r["source"].startswith("MONDO") else "-") + "\033[0m"
                tag = ""
                if r.get("ambiguous") and r["condition"] not in RC.CHOICE: tag = f"   \033[33m{len(r['readings'])} meanings: pick on the next screen\033[0m"
                if read.lower() == r["condition"].lower(): read = ""
                rows.append((r["condition"], org, (f"{read}  " if read else "") + f"\033[90m{how}\033[0m" + tag))
            ow = min(max([_w(re.sub(r"\x1b\[[\d;]*m", "", o)) for _, o, _ in rows] + [6]), 24)
            head = f"  \033[1m{'Input':<{nw}}\033[0m   \033[1m{'Organs':<{ow}}\033[0m   \033[1mRead as\033[0m"
            lines = [head, "\033[90m" + "─" * min(width, nw + ow + 42) + "\033[0m"]
            for k, (c, org, what) in enumerate(rows):
                name = _clip(c, nw); plain = re.sub(r"\x1b\[[\d;]*m", "", org)
                lines.append(("\033[36;1m› \033[0m" if k == cur else "  ") + f"{name}{' ' * (nw - _w(name))}   {org}{' ' * max(0, ow - _w(plain))}   {what}")
            if not self.analysis_cached: lines += ["", f"\033[90m{elapsed:.1f} s\033[0m"]
            panel = gemma_panel(reports[cur], RC, ko, width) if reports[cur].get("gemma") else []
            wrapped = [ln for line in lines for ln in tui._wrap_ansi(line, width)]
            if h - y0 - 4 - len(wrapped) < len(panel) + 1: panel = []            # the panel only when the whole table still fits
            area = max(1, h - y0 - 3 - (len(panel) + 1 if panel else 0)); top = max(0, min(top, len(wrapped) - area))
            for i, ln in enumerate(wrapped[top:top + area]): self.S.put_ansi(y0 + i, 2, ln)
            for i, ln in enumerate(panel): self.S.put_ansi(y0 + min(area, len(wrapped)) + 1 + i, 2, ln)
            self.S.put(h - 2, 2, "AI process   " + self.usage.line(), self.S.dim)
            if len(reports) > 1: self.S.put(h - 1, 2, "↑↓ 입력 고르기", self.S.dim)
            elif len(wrapped) > area: self.S.put(h - 1, 2, f"{top + 1}–{min(top + area, len(wrapped))} / {len(wrapped)}", self.S.dim)
            self.scr.refresh(); key = self.key()
            if key == "UP":
                if len(reports) > 1: cur = max(0, cur - 1)
                else: top = max(0, top - 1)
            elif key == "DOWN":
                if len(reports) > 1: cur = min(len(reports) - 1, cur + 1)
                else: top = min(max(0, len(wrapped) - area), top + 1)
            elif key == "PGUP": return BACK
            elif key == "PGDN": return None


def gemma_panel(r, RC, ko, width):
    """a boxed tree of the Gemma judge's four outputs for one typed condition, and the step that set its organs. The output that
    decided something here is green; the others were computed and are grey. Plain box lines only: no bars or dots, whose width
    differs between terminal fonts."""
    g = r["gemma"]; kr = bool(HANGUL.search(r["condition"])); G, D, E = "\033[32;1m", "\033[90m", "\033[0m"
    nm = lambda t, en: (ko.get(t) if kr else "") or en
    vis = lambda t: _w(re.sub(r"\x1b\[[\d;]*m", "", t))
    import suggest as SG
    pname = {p["id"]: p["name"] for p in SG.profiles()}
    used = dict(valid=True, organ=r["source"] == "AI judgment", align=r.get("via") == "judge vector", sym=False)
    iw = max(30, min(width - 4, 72)); room = iw - 16                 # inside width; room for a value after "  ├─ organ   "
    near_id, near_en, cos = g["near"]; sym_id, sym_p = g["sym"]
    organs = "  ".join((G if p >= t else D) + f"{GLYPH[a]} {p:.2f}" + E for a, p, t in g["organ"])
    named = lambda n, x: f"{_clip(n, max(4, room - 6 - len(x)))}  {D}{x}{E}"
    heads = [("valid", f"{g['valid']:.3f}  " + ((G + "✓" + E) if g["ok"] else ("\033[31m✗" + E))),
             ("organ", organs),
             ("align", named(nm(near_id, near_en), f"cos {cos:.2f}")),
             ("sym", named(nm(sym_id, pname.get(sym_id, sym_id)), f"{sym_p:.2f}"))]
    src = r["source"]
    by = ("Gemma align" if used["align"] else "Gemma organ" if used["organ"] else "Chosen" if src == "Chosen" else
          "MONDO" if src.startswith("MONDO") else "Registry" if src in ("Registry match", "Similar condition") else
          "HPO" if src.startswith("Phenotype") else "Not understood")
    body = ["", _clip(r["condition"], iw - 2)]
    for k, (key, text) in enumerate(heads):
        body.append(("  └─ " if k == 3 else "  ├─ ") + ((G if used[key] else D) + f"{key:<7}" + E) + text)
    body += ["", "→ " + (strip(RC.AXES, r["organs"]) if r["organs"] else D + "-" + E) + f"   {D}{by}{E}", ""]
    title = " Gemma judge "; iw = max(_w(title) + 4, min(iw, max(vis(ln) for ln in body) + 3))       # as wide as its content
    out = [D + "┌─" + E + title + D + "─" * max(0, iw - _w(title) - 1) + "┐" + E]
    for ln in body: out.append(D + "│" + E + " " + ln + " " * max(0, iw - 1 - vis(ln)) + D + "│" + E)
    return out + [D + "└" + "─" * iw + "┘" + E]

def run(RC, back=False):
    """-> (conditions, raw labs) or None. back: reopen at the last step (priority if it applies, else lab values), entries kept."""
    def app(scr):
        F = Form(scr, RC); st = load(); st["picked"] &= set(RC._reg); step = 0
        kn = RC.condition_name                                       # a picked disease keeps the name it was picked by
        RC.CHOICE.update(st["choice"])
        if back:
            conds = [i for i in RC._reg if i in st["picked"]] + split_free(st["free"]); F.loading("불러오는 중 ...")
            pc = RC.patient_conditions(conds, st["raw"])
            step = 3 if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2 else 1
        while True:
            F.done = []
            if step >= 1: F.done.append(("기저질환", ", ".join([RC.condition_name(i) for i in sorted(st["picked"], key=list(RC._reg).index)] + [kn(c) for c in split_free(st["free"])])))
            if step >= 2:
                F.done.append(("검사 수치", f"{len(st['raw'])}개 입력" if st["raw"] else "입력 없음"))
            conds = [i for i in RC._reg if i in st["picked"]] + split_free(st["free"])
            if step == 0:
                r = F.conditions(st["picked"], st["free"], st["choice"])
                if r == QUIT: return None
                for c in st["choice"]: RC.CHOICE.pop(c, None)                # a name picked from the suggestions is that concept
                st["picked"], st["free"], st["choice"] = r; RC.CHOICE.update(st["choice"]); save(st); step = 1
            elif step == 1:
                r = F.labs(st["raw"])
                if r == BACK: step = 0; continue
                st["raw"] = r; save(st); step = 2
            elif step == 2:                                       # free text that maps to no organ
                RC.FALLBACK = {}
                reports = []
                if split_free(st["free"]):
                    analysis = F.analyze(conds)
                    if analysis == BACK: step = 0; continue
                    reports, elapsed = analysis
                    if F.analysis_review(reports, elapsed) == BACK: step = 0; continue
                    groups = [g for g in RC.ambiguous_conditions(conds) if g[0] not in st["choice"]]   # typed texts with readings on different organs: the user picks
                    if groups:
                        applied = {r["condition"]: o["mondo"] for r in reports for o in r.get("readings", []) if o["name"] == r["name"]}
                        pick = F.meanings(groups, {**applied, **RC.CHOICE})
                        if pick == BACK: step = 0; continue
                        RC.CHOICE.update(pick)
                        F.done.append(("질환 확인", ", ".join(f"{c} → {next((r['name'] for r in o if r['mondo'] == pick[c]), '모름')}" for c, o in groups)))
                miss = RC.unresolved(conds) if split_free(st["free"]) else []
                if miss and RC.HAS_LEARNED:                       # no organ found: the learned estimate on the 'auto' terms, without asking
                    RC.FALLBACK = {c: RC.AUTO_FALLBACK for c in miss}
                step = 3; st["miss"] = bool(miss)
            elif step == 3:                                       # priority between conditions on different organs
                pc = RC.patient_conditions(conds, st["raw"]); RC.PRIORITY = {}
                if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2:
                    d = RC.default_levels(pc); names = [c for c, _, _ in pc]
                    show = kn
                    lv0 = RC.default_levels(pc); nw = max(_w(kn(c)) for c, _, _ in pc)
                    auto = "\n".join(f"  \033[1m{lv0[c]}\033[0m   {kn(c)}{' ' * (nw - _w(kn(c)))}   {strip(RC.AXES, o)}" for c, o, _ in sorted(pc, key=lambda x: lv0[x[0]]))
                    k = F.choose("질환 우선순위", "장기가 다른 질환이 여럿입니다. ADC 경고를 비교할 때 어느 질환의 장기를 먼저 볼지 정합니다.\n\n" + auto,
                                 ["자동 · 질환 심각도 순", "직접 정하기"])
                    if k == BACK: step = 2 if st.get("miss") else 1; continue
                    if k == 1:
                        lv = F.order([show(c) for c in names], [", ".join(RC.EN[a] for a in sorted(o, key=RC.AXES.index)) for _, o, _ in pc], [d[c] for c in names], [o for _, o, _ in pc])
                        if lv == BACK: continue
                        RC.PRIORITY = dict(zip(names, lv))
                return conds, st["raw"]
    return curses.wrapper(app)
