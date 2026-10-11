"""One-screen input for ml/recommend.py: each step opens below the finished ones, ESC goes back a step.

Steps: conditions (organ-grouped list; 'Other' at the bottom opens a typing line on the same screen) -> lab values (typed in
place, units as on a lab report) -> [FinnGen estimate for a condition that maps to no organ] -> [priority between conditions].
Returns (conditions, raw lab values) and sets recommend.FALLBACK / recommend.PRIORITY, or None if the user quits.
"""
import curses
from tui import _Screen, _cw, _clip, _wrap, _enter

BACK, QUIT = "back", "quit"
SAVE = __import__("os").path.expanduser("~/.config/adctox/last_input.json")      # entries of the run in progress; deleted once results are shown


def load():
    import json
    try:
        d = json.load(open(SAVE)); return dict(picked=set(d.get("picked", [])), free=d.get("free", ""), raw=d.get("raw", {}))
    except (OSError, ValueError): return dict(picked=set(), free="", raw={})


def clear():
    """forget the entries: called as soon as the result table has been shown."""
    import os
    try: os.remove(SAVE)
    except OSError: pass


def save(st):
    import json, os
    try:
        os.makedirs(os.path.dirname(SAVE), exist_ok=True)
        json.dump(dict(picked=sorted(st["picked"]), free=st["free"], raw=st["raw"]), open(SAVE, "w"), ensure_ascii=False)
    except OSError: pass


def _w(s): return sum(_cw(c) for c in s)


def _key(scr):
    try: k = scr.get_wch()
    except curses.error: return None
    if isinstance(k, str):
        if k in ("\n", "\r"): return "ENTER"
        if k == "\x1b": return "ESC"
        if k in ("\x7f", "\x08"): return "BS"
        if k == "\t": return "DOWN"
        return k
    return {curses.KEY_UP: "UP", curses.KEY_DOWN: "DOWN", curses.KEY_BACKSPACE: "BS", curses.KEY_ENTER: "ENTER",
            curses.KEY_LEFT: "LEFT", curses.KEY_RIGHT: "RIGHT", curses.KEY_PPAGE: "PGUP", curses.KEY_NPAGE: "PGDN"}.get(k)


def split_free(text):
    """'copd ,   asthma,heart  stop' -> ['copd', 'asthma', 'heart stop']"""
    return [" ".join(x.split()) for x in text.split(",") if x.strip()]


class Form:
    def __init__(self, scr, RC):
        self.S, self.scr, self.RC = _Screen(scr), scr, RC
        self.done = []                      # [(step title, summary)] shown above the current step

    def frame(self, title, hint):
        """draw the finished steps and the current step's title; -> first free row."""
        h, w = self.scr.getmaxyx(); self.scr.clear(); y = 0          # full repaint: ambiguous-width glyphs leave debris otherwise
        for t, s in self.done:
            for k, ln in enumerate(_wrap(f"✓ {t}: {s}", w - 2, "    ")[:2]): self.S.put(y, 1, ln, self.S.dim); y += 1
        if self.done: y += 1
        self.S.put(y, 1, title, self.S.title); y += 1
        if hint: self.S.put(y, 1, hint, self.S.dim); y += 1
        return y + 1

    # ------------------------------------------------------------------ step 1
    def conditions(self, picked, free):
        RC = self.RC; items = []                                      # (kind, value, text)
        by = {}
        for i in RC._reg: by.setdefault(RC._reg[i]["organ_axes"].split(";")[0], []).append(i)
        lw = max(len(RC._reg[i]["label"]) for i in RC._reg)
        for organ in RC.AXES:
            if organ not in by: continue
            items.append(("head", organ, RC.EN[organ]))
            for i in by[organ]: items.append(("cond", i, f"{RC._reg[i]['label']:<{lw}}   {RC.KO.get(i, '')}"))
        items.append(("head", None, "")); items.append(("other", None, "Other (type in English)"))
        sel = [k for k, it in enumerate(items) if it[0] != "head"]; cur = 0; picked = set(picked); typing = False; query = None; note = ""
        while True:
            shown = [k for k in sel if items[k][0] == "other" or query.lower() in items[k][2].lower()] if query else list(range(len(items)))
            pick_rows = [k for k in shown if items[k][0] != "head"]
            if not pick_rows: pick_rows = [sel[-1]]; shown = pick_rows
            cur = min(cur, len(pick_rows) - 1); at = pick_rows[cur]
            y0 = self.frame("기저질환", "↑↓ 이동   SPACE 선택   / 검색   PgDn 다음 단계   ESC 나가기")
            h, w = self.scr.getmaxyx(); bottom = 3; area = max(3, h - y0 - bottom)
            pos = shown.index(at); top = max(0, min(pos - area // 2, len(shown) - area))
            for r, k in enumerate(shown[top:top + area]):
                kind, val, text = items[k]; on = k == at
                if kind == "head": self.S.put(y0 + r, 2, text, self.S.title); continue
                mark = "x" if (val in picked if kind == "cond" else bool(free.strip())) else " "
                label = text if kind == "cond" else (f"{text}: {', '.join(split_free(free))}" if free.strip() and not typing else text)
                self.S.put(y0 + r, 0, f" {'→' if on else ' '} [{mark}] {label}", self.S.cur if on else 0)
            yb = h - bottom
            if typing:
                self.S.put(yb, 1, "Other — 쉼표로 구분 (예: copd, asthma)   ENTER 완료", self.S.dim)
                self.S.put(yb + 1, 1, "> " + free + "_", self.S.cur)
            elif query is not None:
                self.S.put(yb + 1, 1, f"/{query}_   (ENTER 검색 유지, ESC 지우기)", self.S.dim)
            n = len(picked) + len(split_free(free))
            self.S.put(h - 1, 1, f"{n} selected" + (f"   {note}" if note else ""), self.S.dim); note = ""
            self.scr.refresh(); k = _key(self.scr)
            if typing:
                if k == "ENTER": typing = False
                elif k == "ESC": typing = False
                elif k == "BS": free = free[:-1]
                elif isinstance(k, str) and len(k) == 1 and k.isprintable(): free += k
                continue
            if query is not None and getattr(self, "_searching", False):
                if k == "ENTER":
                    self._searching = False
                    if not query: query = None
                elif k == "ESC": query = None; self._searching = False
                elif k == "BS": query = query[:-1]
                elif k in ("UP", "DOWN"): cur = max(0, min(len(pick_rows) - 1, cur + (1 if k == "DOWN" else -1)))
                elif isinstance(k, str) and len(k) == 1 and k.isprintable(): query += k; cur = 0
                continue
            if k == "UP": cur = max(0, cur - 1)
            elif k == "DOWN": cur = min(len(pick_rows) - 1, cur + 1)
            elif k == "PGDN":
                if picked or split_free(free): return picked, free
                note = "하나 이상 고르세요"
            elif k == "/": query = ""; self._searching = True; cur = 0
            elif k == " ":
                kind, val, _ = items[at]
                if kind == "cond": picked ^= {val}
                else: typing = True
            elif k == "ENTER":
                if items[at][0] == "other" and not free.strip(): typing = True; continue
                if query is not None:                                       # leave the filter, stay on the same item
                    query = None; full = [j for j in range(len(items)) if items[j][0] != "head"]; cur = full.index(at); continue
                if picked or split_free(free): return picked, free
                note = "하나 이상 고르세요"
            elif k == "ESC":
                if query is not None: query = None
                else: return QUIT

    # ------------------------------------------------------------------ step 2
    def labs(self, raw):
        import labs as LB
        fields = LB.FIELDS; show = lambda v: ("y" if v else "n") if isinstance(v, bool) else (f"{v:g}" if isinstance(v, float) else str(v))
        vals = {k: "" if raw.get(k) is None else show(raw[k]) for k, *_ in fields}
        rows = []                                                      # ("head", group) / ("field", index) / ("done",)
        g = None
        for i, (k, label, unit, grp) in enumerate(fields):
            if grp != g: rows.append(("head", grp)); g = grp
            rows.append(("field", i))
        rows.append(("done",)); pick = [r for r, x in enumerate(rows) if x[0] != "head"]; cur = 0; note = ""
        lw = max(len(l) for _, l, _, _ in fields)
        while True:
            at = pick[cur]
            y0 = self.frame("검사 수치 (아는 것만)", "↑↓ 이동   값 입력   ENTER 다음 칸   PgUp 이전 단계   PgDn 다음 단계")
            h, w = self.scr.getmaxyx(); area = max(3, h - y0 - 2); top = max(0, min(at - area // 2, len(rows) - area))
            for r, x in enumerate(rows[top:top + area]):
                row = top + r; on = row == at
                if x[0] == "head": self.S.put(y0 + r, 2, x[1], self.S.title)
                elif x[0] == "done": self.S.put(y0 + r, 0, f" {'→' if on else ' '} [ 완료 ]", self.S.cur if on else 0)
                else:
                    k, label, unit, _ = fields[x[1]]; v = vals[k]
                    self.S.put(y0 + r, 0, f" {'→' if on else ' '} {label:<{lw}}  {v + ('_' if on else ''):<10} {unit}", self.S.cur if on else 0)
            parsed = {}
            for key, v in vals.items():                                 # a value still being typed ("0", "0.") is just left out
                try:
                    if v.strip(): parsed[key] = LB.parse(key, v)
                except ValueError: pass
            try: info = "   ".join(n for n in LB.derive(parsed)[2] if n.startswith("CLcr"))
            except Exception: info = ""
            self.S.put(h - 1, 1, note or info, self.S.dim); note = ""
            self.scr.refresh(); k = _key(self.scr)
            x = rows[at]
            if k == "UP": cur = max(0, cur - 1)
            elif k == "DOWN": cur = min(len(pick) - 1, cur + 1)
            elif k in ("PGUP", "ESC"): return BACK
            elif k == "ENTER" or k == "PGDN":
                if x[0] == "done" or k == "PGDN":
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
            y0 = self.frame(title, "↑↓ 이동   ENTER 선택   PgUp 이전 단계   PgDn 다음 단계")
            h, w = self.scr.getmaxyx()
            for ln in _wrap(desc, w - 4, "  ") if desc else []: self.S.put(y0, 2, ln, self.S.dim); y0 += 1
            if desc: y0 += 1
            for i, o in enumerate(options): self.S.put(y0 + i, 0, f" {'→' if i == cur else ' '} ({'●' if i == cur else '○'}) {o}", self.S.cur if i == cur else 0)
            self.scr.refresh(); k = _key(self.scr)
            if k == "UP": cur = max(0, cur - 1)
            elif k == "DOWN": cur = min(len(options) - 1, cur + 1)
            elif k in ("ENTER", " ", "PGDN"): return cur
            elif k in ("ESC", "PGUP"): return BACK

    def order(self, names, details, levels):
        lv = list(levels); n = len(names); it = 0
        while True:
            y0 = self.frame("어느 질환 쪽 독성을 먼저 피할까요?  (1 = 먼저, 같은 숫자 = 같은 순위)", "↑↓ 이동   ←→ 순위 변경   PgUp 이전 단계   PgDn 다음 단계")
            order = sorted(range(n), key=lambda i: (lv[i], i)); pos = order.index(it); w0 = max(_w(x) for x in names)
            for r, i in enumerate(order):
                on = i == it; self.S.put(y0 + r, 0, f" {'→' if on else ' '} {lv[i]:>2}   {names[i]}{' ' * (w0 - _w(names[i]))}   {details[i]}", self.S.cur if on else 0)
            self.scr.refresh(); k = _key(self.scr)
            if k == "UP": it = order[max(0, pos - 1)]
            elif k == "DOWN": it = order[min(n - 1, pos + 1)]
            elif k in ("LEFT", "-"): lv[it] = max(1, lv[it] - 1)
            elif k in ("RIGHT", "+", "="): lv[it] = min(n, lv[it] + 1)
            elif k in ("ENTER", "PGDN"): d = {v: j for j, v in enumerate(sorted(set(lv)), 1)}; return [d[v] for v in lv]
            elif k in ("ESC", "PGUP"): return BACK

    def loading(self, text):
        y0 = self.frame(text, ""); self.scr.refresh()


def run(RC, back=False):
    """-> (conditions, raw labs) or None. back: reopen at the last step (priority if it applies, else lab values), entries kept."""
    def app(scr):
        curses.curs_set(0); F = Form(scr, RC); st = load(); st["picked"] &= set(RC._reg); step = 0
        if back:
            conds = [i for i in RC._reg if i in st["picked"]] + split_free(st["free"]); F.loading("불러오는 중 ...")
            pc = RC.patient_conditions(conds, st["raw"])
            step = 3 if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2 else 1
        while True:
            F.done = []
            if step >= 1: F.done.append(("기저질환", ", ".join([RC._reg[i]["label"] for i in sorted(st["picked"], key=list(RC._reg).index)] + split_free(st["free"]))))
            if step >= 2:
                import labs as LB
                nm = {k: l for k, l, _, _ in LB.FIELDS}
                fmt = lambda v: ("y" if v else "n") if isinstance(v, bool) else (f"{v:g}" if isinstance(v, float) else str(v))
                F.done.append(("검사 수치", ", ".join(f"{nm[k]} {fmt(v)}" for k, v in st["raw"].items()) or "없음"))
            conds = [i for i in RC._reg if i in st["picked"]] + split_free(st["free"])
            if step == 0:
                r = F.conditions(st["picked"], st["free"])
                if r == QUIT: return None
                st["picked"], st["free"] = r; save(st); step = 1
            elif step == 1:
                r = F.labs(st["raw"])
                if r == BACK: step = 0; continue
                st["raw"] = r; save(st); step = 2
            elif step == 2:                                       # free text that maps to no organ
                if split_free(st["free"]): F.loading("질환 해석 모델 불러오는 중 ...")
                miss = RC.unresolved(conds) if split_free(st["free"]) else []
                RC.FALLBACK = {}
                if miss and RC.HAS_LEARNED:
                    k = F.choose(f"관련 장기를 찾지 못함: {', '.join(miss)}", "FinnGen 모델 추정 장기를 쓸까요? (검증 안 됨, 오타에도 값이 나오니 철자 확인)",
                                 [n for n, _ in RC.FALLBACK_OPTS])
                    if k == BACK: step = 1; continue
                    f = RC.FALLBACK_OPTS[k][1]; RC.FALLBACK = {c: f for c in miss} if f > 0 else {}
                    F.done.append(("추정 장기", RC.FALLBACK_OPTS[k][0]))
                step = 3; st["miss"] = bool(miss)
            elif step == 3:                                       # priority between conditions on different organs
                pc = RC.patient_conditions(conds, st["raw"]); RC.PRIORITY = {}
                if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2:
                    d = RC.default_levels(pc); names = [c for c, _, _ in pc]
                    show = lambda c: RC._reg[c]["label"] if c in RC._reg else c
                    auto = "  ".join(f"{d[c]} {show(c)}" for c in sorted(names, key=lambda c: d[c]))
                    k = F.choose("질환 우선순위", f"자동: {auto}", ["자동 (질환 심각도 순)", "직접 정하기"])
                    if k == BACK: step = 2 if st.get("miss") else 1; continue
                    if k == 1:
                        lv = F.order([show(c) for c in names], [", ".join(RC.EN[a] for a in sorted(o, key=RC.AXES.index)) for _, o, _ in pc], [d[c] for c in names])
                        if lv == BACK: continue
                        RC.PRIORITY = dict(zip(names, lv))
                return conds, st["raw"]
    return curses.wrapper(app)
