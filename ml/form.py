"""One-screen input for ml/recommend.py: each step opens below the finished ones, ESC goes back a step.

Steps: conditions (organ-grouped list; 'Other' at the bottom opens a typing line on the same screen) -> lab values (typed in
place, units as on a lab report) -> [learned estimate for a condition that maps to no organ] -> [priority between conditions].
Returns (conditions, raw lab values) and sets recommend.FALLBACK / recommend.PRIORITY, or None if the user quits.
"""
from term import curses
from tui import _Screen, _cw, _clip, _wrap, _enter

BACK, QUIT = "back", "quit"
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
        if not APP_CHECK and RC.HAS_LEARNED: APP_CHECK["started"] = True; __import__("threading").Thread(target=_check_app, daemon=True).start()
        self.S, self.scr, self.RC = _Screen(scr), scr, RC
        self.done = []                      # [(step title, summary)] shown above the current step
        self.usage = _ProcessUsage()
        self.analysis_cached = False

    def frame(self, title, hint):
        """draw the finished steps and the current step's title; -> first free row."""
        self.scr.erase(); h, w = self.scr.getmaxyx(); y = 5
        self.S.brand()
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
        """disease input: names are suggested while typing (TAB switches to a search by symptoms or a sentence).
        -> (registry ids, free text 'a, b', {free text: chosen MONDO id}) or QUIT."""
        import threading, time, suggest as SG
        RC = self.RC; choice = dict(choice or {})
        sel = [("reg", i, RC.condition_name(i), RC._reg[i]["organ_axes"].split(";")) for i in RC._reg if i in picked]
        sel += [("mondo" if f in choice else "text", choice.get(f, f), f, []) for f in split_free(free)]
        mode, query, cur, note, kept = "name", "", 0, "", {}
        found, ai, sym = [], dict(q=None, res=[], busy=False), dict(q=None, res=None, busy=False, error="")
        typed_at = 0.0; ai_on = RC.HAS_LEARNED
        threading.Thread(target=SG.index(RC).load_mondo, daemon=True).start()       # MONDO and KCD names, about 2 s
        organ = lambda org: ", ".join(RC.ORGAN_KO.get(a, a) for a in org)

        def run_ai(q):
            try: res = SG.semantic(RC, q)
            except Exception: res = []
            if ai["q"] == q: ai["res"] = res
            ai["busy"] = False

        def run_sym(q):
            try: sym["res"] = SG.symptoms(RC, q, semantic=RC.HAS_LEARNED); sym["error"] = ""
            except Exception as e: sym["res"] = []; sym["error"] = f"{type(e).__name__}: {str(e)[:80]}"
            sym["busy"] = False

        def add(s):
            kind, val, label, _, org = s[:5]
            if any((x[0], x[1]) == (kind, val) or x[2].lower() == label.lower() for x in sel): return f"이미 선택됨: {label}"
            sel.append((kind, val, label, org)); return f"추가: {label}"

        self.scr.timeout(100)
        try:
            while True:
                if mode == "name":
                    rows = [("s", s, "") for s in found]
                    if ai["q"] == query.strip() and ai["res"]:
                        have = {(s[0], s[1]) for s in found}
                        rows += [("s", s, "AI") for s in ai["res"] if (s[0], s[1]) not in have]
                    split = SG.parts(RC, query)
                    if split: rows.insert(0, ("split", ("text", split, "각각 따로 추가: " + ", ".join(split), "", []), ""))
                    if query.strip(): rows.append(("raw", ("text", query.strip(), query.strip(), "", []), ""))
                else:
                    rows = [("s", s, why) for s, why in (sym["res"] or [])] if sym["q"] == query.strip() else []
                rows += [("sel", x, "") for x in sel]
                cur = max(0, min(cur, len(rows) - 1))
                y = self.frame("기저질환", "↑↓ 이동   ENTER 추가 / 빼기   TAB 질환명 ↔ 증상·문장   PgDn 다음 단계   ESC 지우기 / 나가기")
                h, w = self.scr.getmaxyx()
                tabs = [("name", "질환명으로 찾기"), ("symptom", "증상·문장으로 찾기")]
                x = 2
                for m, t in tabs:
                    lab = f" {t} "; self.S.put(y, x, lab, self.S.cur if m == mode else self.S.dim); x += _w(lab) + 2
                y += 1
                self.S.put(y, 2, "질환명을 입력하면 바로 아래에 추천합니다. 한국어, 영어, 약어, 오타 모두 됩니다." if mode == "name" else
                           "증상, 치료, 문장을 쓰고 ENTER   예) 숨이 차고 다리가 부어요, 투석 중", self.S.dim); y += 2
                self.S.put(y, 2, "> " + query + "_", self.S.title); y += 2
                status = ""
                if mode == "name" and ai["busy"]: status = "AI 추천 찾는 중 ..."
                if mode == "symptom" and sym["busy"]: status = "증상으로 질환 찾는 중 ... (처음 한 번은 모델을 불러 10초 정도 걸립니다)"
                if mode == "symptom" and sym["error"]: status = "검색 실패: " + sym["error"]
                if mode == "symptom" and not sym["busy"] and sym["q"] == query.strip() and query.strip() and not sym["res"]: status = "맞는 질환을 찾지 못했습니다. 다르게 써 보거나 질환명으로 찾기를 쓰세요."
                lw = max([_w(r[1][2]) for r in rows] + [10]); lw = min(lw, max(10, w // 2 - 6))
                ow = max([_w(organ(r[1][3] if r[0] == "sel" else r[1][4])) for r in rows if r[0] not in ("raw", "split")] + [4])
                area = max(3, h - y - 3); top = max(0, min(cur - area // 2, len(rows) - area)); shown_sel_head = False
                lines = []
                for k, (kind, s, tag) in enumerate(rows):
                    if kind == "sel" and not shown_sel_head:
                        lines.append(("head", f"선택한 질환 {len(sel)}개")); shown_sel_head = True
                    lines.append((k, kind, s, tag))
                if rows and rows[0][0] != "sel": lines.insert(0, ("head", "추천" if mode == "name" else "추천 (증상·문장)"))
                at = next(i for i, l in enumerate(lines) if l[0] == cur) if rows else 0
                top = max(0, min(at - area // 2, len(lines) - area))
                for r, l in enumerate(lines[top:top + area]):
                    yy = y + r
                    if l[0] == "head": self.S.put(yy, 2, l[1], self.S.title); continue
                    k, kind, s, tag = l; on = k == cur; label = _clip(s[2], lw)
                    if kind == "raw": text = f"입력한 그대로 추가: {s[2]}"
                    elif kind == "split": text = s[2]
                    else:
                        extra = s[3] if kind == "s" and s[3] and s[3] != s[2] else ""
                        org = organ(s[3] if kind == "sel" else s[4])
                        ex = _clip(extra, 24)
                        if kind == "sel": text = f"✓ {label}{' ' * (lw - _w(label))}   {org}"
                        else: text = f"{label}{' ' * (lw - _w(label))}   {ex}{' ' * (24 - _w(ex))}  {org}{' ' * (ow - _w(org))}" + (f"   \033[90m{tag}\033[0m" if tag else "")
                    self.S.row(yy, f" {'→' if on else ' '} {text}", on)
                n = len(sel)
                update_hint = "   Ctrl+U 모델 업데이트" if RC.HAS_LEARNED else ""
                if APP_CHECK.get("newer"): update_hint += f"   새 앱 {APP_CHECK['latest']}: adctox --update-app"
                self.S.put(h - 2, 1, status, self.S.dim)
                self.S.put(h - 1, 1, f"{n}개 선택" + update_hint + (f"   {note}" if note else ""), self.S.dim)
                self.scr.refresh(); k = _key(self.scr, tab=True)
                if k is None:                                              # no key within 0.1 s: start the AI search after a pause
                    q = query.strip()
                    if mode == "name" and ai_on and len(q) >= 2 and ai["q"] != q and not ai["busy"] and time.monotonic() - typed_at > 0.35:
                        ai.update(q=q, res=[], busy=True); threading.Thread(target=run_ai, args=(q,), daemon=True).start()
                    continue
                note = ""
                if k == "TAB":                                             # each mode keeps its own text
                    kept[mode] = query; mode = "symptom" if mode == "name" else "name"; query = kept.get(mode, ""); cur = 0
                    if mode == "name": found = SG.names(RC, query)
                    continue
                if k == "UP": cur = max(0, cur - 1)
                elif k == "DOWN": cur = min(len(rows) - 1, cur + 1)
                elif k == "PGDN":
                    if sel: return self._split(sel)
                    note = "질환을 하나 이상 추가하세요"
                elif k == "ESC":
                    if query: query, found, cur = "", [], 0
                    else: return QUIT
                elif k == "\x15" and RC.HAS_LEARNED: self.model_updates()
                elif k == "ENTER":
                    if mode == "symptom" and query.strip() and sym["q"] != query.strip() and not sym["busy"]:
                        sym.update(q=query.strip(), res=None, busy=True); threading.Thread(target=run_sym, args=(query.strip(),), daemon=True).start(); cur = 0; continue
                    if not rows: note = "질환명을 입력하세요" if mode == "name" else "증상이나 문장을 입력하세요"; continue
                    kind, s, _ = rows[cur]
                    if kind == "sel": sel.remove(s); note = f"뺌: {s[2]}"
                    elif kind == "split":
                        note = "   ".join(add(("text", w, w, "", [])) for w in s[1]); query, found, cur = "", [], 0
                    else:
                        note = add(s)
                        if mode == "name": query, found, cur = "", [], 0
                elif k == "BS":
                    query = query[:-1]; typed_at = time.monotonic(); cur = 0
                    if mode == "name": found = SG.names(RC, query)
                elif isinstance(k, str) and len(k) == 1 and k.isprintable():
                    query += k; typed_at = time.monotonic(); cur = 0
                    if mode == "name": found = SG.names(RC, query)
        finally:
            self.scr.timeout(-1)

    def _split(self, sel):
        picked = {x[1] for x in sel if x[0] == "reg"}
        free = [x[2] for x in sel if x[0] != "reg"]
        choice = {x[2]: x[1] for x in sel if x[0] == "mondo"}
        return picked, ", ".join(free), choice

    def model_updates(self):
        """Update from a dedicated screen without changing the patient's current input."""
        import adc_updates as updates
        import threading
        state = {"phase": "idle", "message": "", "manifest": None, "changed": False, "plan": None}
        cancel = threading.Event()
        selection = 0
        busy = ("checking", "downloading", "restoring")

        def start(action):
            cancel.clear()
            state["phase"] = {"check": "checking", "update": "downloading", "rollback": "restoring"}[action]
            def worker():
                try:
                    if action == "check":
                        state["manifest"] = updates.fetch_manifest(); todo = updates.plan(state["manifest"]); state["plan"] = todo
                        state["message"] = ("최신 상태입니다. 다운로드할 파일이 없습니다." if todo["up_to_date"] else
                                            f"변경 파일 {len(todo['download'])}개 ({todo['download_bytes'] / 1024**2:.1f} MiB)만 다운로드합니다. 그대로 쓰는 파일 {len(todo['reuse'])}개")
                    elif action == "update":
                        def progress(name, done, total):
                            if cancel.is_set(): raise updates.UpdateError("업데이트를 취소했습니다.")
                            state["message"] = f"{name}   {done / 1024**2:.1f} / {total / 1024**2:.1f} MiB"
                        result = updates.install(state["manifest"], progress=progress, cancelled=cancel.is_set)
                        state["message"] = "최신 상태입니다." if result.get("up_to_date") else f"{len(result['downloaded'])} files updated   {len(result['reused'])} unchanged"
                        state["changed"] = not result.get("up_to_date")
                        state["plan"] = updates.plan(state["manifest"])
                    else:
                        version = updates.rollback()
                        state["message"] = f"이전 모델 {version} 복원 완료"
                        state["changed"] = True
                    state["phase"] = "ready"
                except Exception as error:
                    state["message"] = str(error)
                    state["phase"] = "error"
            threading.Thread(target=worker, daemon=True).start()

        start("check")
        self.scr.timeout(100)
        try:
            while True:
                if state["changed"]:
                    self.RC.clear_model_cache()
                    state["changed"] = False
                y = self.frame("모델 업데이트", "↑↓ 선택   ENTER 실행   ESC 돌아가기")
                info = updates.current_info()
                current = info["model_version"] if info else "Research cache"
                latest = state["manifest"]["model_version"] if state["manifest"] else "-"
                self.S.put(y, 2, f"Installed   {current}", self.S.title)
                self.S.put(y + 1, 2, f"Available   {latest}", self.S.dim)
                phase = state["phase"]
                latest_ok = bool(state.get("plan") and state["plan"]["up_to_date"])
                labels = (("다시 확인" if latest_ok else "업데이트"), "이전 모델로 복원", "돌아가기") if state["manifest"] else ("다시 확인", "이전 모델로 복원", "돌아가기")
                for i, label in enumerate(labels): self.S.row(y + 3 + i, f" {'>' if i == selection else ' '} {label}", i == selection)
                message = {"checking": "업데이트 확인 중 ...", "downloading": "다운로드 및 검증 중 ...", "restoring": "이전 모델 확인 중 ..."}.get(phase, "")
                for i, line in enumerate(_wrap(message + ("\n" if message else "") + state["message"], max(2, self.scr.getmaxyx()[1] - 5))):
                    self.S.put(y + 8 + i, 2, line, self.S.dim)
                self.scr.refresh()
                key = _key(self.scr)
                if phase in busy:
                    if key == "ESC" and phase == "downloading": cancel.set(); state["message"] = "취소 중 ..."
                    elif key == "ESC" and phase == "checking": return
                    continue
                if key == "UP": selection = max(0, selection - 1)
                elif key == "DOWN": selection = min(2, selection + 1)
                elif key == "ESC" or (key == "ENTER" and selection == 2): return
                elif key == "ENTER": start("rollback" if selection == 1 else ("update" if state["manifest"] and not latest_ok else "check"))
        finally:
            self.scr.timeout(-1)

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
                elif x[0] == "done": self.S.row(y0 + r, f" {'→' if on else ' '} [ 완료 ]", on)
                else:
                    k, label, unit, _ = fields[x[1]]; v = vals[k]
                    self.S.row(y0 + r, f" {'→' if on else ' '} {label:<{lw}}  {v + ('_' if on else ''):<10} {unit}", on)
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
            for paragraph in desc.splitlines() if desc else []:
                for ln in _wrap(paragraph, w - 5, "    "): self.S.put(y0, 2, ln, self.S.dim); y0 += 1
            if desc: y0 += 1
            for i, o in enumerate(options): self.S.row(y0 + i, f" {'→' if i == cur else ' '} ({'●' if i == cur else '○'}) {o}", i == cur)
            self.scr.refresh(); k = _key(self.scr)
            if k == "UP": cur = max(0, cur - 1)
            elif k == "DOWN": cur = min(len(options) - 1, cur + 1)
            elif k in ("ENTER", " ", "PGDN"): return cur
            elif k in ("ESC", "PGUP"): return BACK

    def meanings(self, groups, chosen):
        """one screen for every typed text that reads as several diseases. groups: [(text, readings)]; chosen: {text: id or None}.
        -> {text: id or None (unknown)} or BACK."""
        RC = self.RC; pick = {}; rows = []                      # ("head", text) / ("opt", text, id, label, organs, tag)
        for g, (text, opts) in enumerate(groups):
            if g: rows.append(("gap",))
            rows.append(("head", text))
            for r in opts:
                name = r["name"][:1].upper() + r["name"][1:]
                rows.append(("opt", text, r["mondo"], name, ", ".join(RC.ORGAN_SHORT[a] for a in r["organs"]) or "장기 없음", "증상" if str(r["mondo"]).startswith("HP:") else ""))
            rows.append(("opt", text, None, "모름", "", ""))
            ids = [r["mondo"] for r in opts]; pick[text] = chosen.get(text, ids[0]) if chosen.get(text, ids[0]) in ids + [None] else ids[0]
        sel = [i for i, x in enumerate(rows) if x[0] == "opt"]; cur = 0
        nw = max(_w(x[3]) + (_w(x[5]) + 3 if x[5] else 0) for x in rows if x[0] == "opt")
        while True:
            y0 = self.frame("입력하신 질환 확인", "↑↓ 이동   ENTER 선택   PgUp 질환 수정   PgDn 다음 단계")
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
                self.S.row(y, f" {'→' if on else ' '}  {mark}  {name}{' ' * (nw - _w(name))}   {x[4]}", on)
            self.scr.refresh(); k = _key(self.scr)
            if k == "UP": cur = max(0, cur - 1)
            elif k == "DOWN": cur = min(len(sel) - 1, cur + 1)
            elif k in ("ENTER", " "):
                x = rows[at]; pick[x[1]] = x[2]
                nxt = [j for j, i in enumerate(sel) if i > at and rows[i][1] != x[1]]   # jump to the next question's current pick, or finish
                if nxt: g = rows[sel[nxt[0]]][1]; cur = next((j for j in nxt if rows[sel[j]][1] == g and rows[sel[j]][2] == pick[g]), nxt[0])
                elif k == "ENTER": return pick
            elif k == "PGDN": return pick
            elif k in ("ESC", "PGUP"): return BACK

    def order(self, names, details, levels):
        lv = list(levels); n = len(names); it = 0
        while True:
            y0 = self.frame("어느 질환 쪽 독성을 먼저 피할까요?  (1 = 먼저, 같은 숫자 = 같은 순위)", "↑↓ 이동   ←→ 순위 변경   PgUp 이전 단계   PgDn 다음 단계")
            order = sorted(range(n), key=lambda i: (lv[i], i)); pos = order.index(it); w0 = max(_w(x) for x in names)
            for r, i in enumerate(order):
                on = i == it; self.S.row(y0 + r, f" {'→' if on else ' '} {lv[i]:>2}   {names[i]}{' ' * (w0 - _w(names[i]))}   {details[i]}", on)
            self.scr.refresh(); k = _key(self.scr)
            if k == "UP": it = order[max(0, pos - 1)]
            elif k == "DOWN": it = order[min(n - 1, pos + 1)]
            elif k in ("LEFT", "-"): lv[it] = max(1, lv[it] - 1)
            elif k in ("RIGHT", "+", "="): lv[it] = min(n, lv[it] + 1)
            elif k in ("ENTER", "PGDN"): d = {v: j for j, v in enumerate(sorted(set(lv)), 1)}; return [d[v] for v in lv]
            elif k in ("ESC", "PGUP"): return BACK

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
        import tui
        top = 0
        while True:
            y0 = self.frame("AI 장기 분석 결과", "↑↓ 스크롤   PgUp 질환 수정   PgDn 다음 단계")
            h, w = self.scr.getmaxyx(); width = max(2, w - 5)
            model_name = "BioLORD + disease-pair MLP" if any(r["model"] for r in reports) else "Disease name matching"
            duration = "Cached" if self.analysis_cached else f"{elapsed:.1f} s"
            self.S.put(y0, 2, f"{model_name}   {duration}", self.S.dim); y0 += 2
            lines = []
            for report in reports:
                lines.append(f"\033[33;1m{report['condition']}\033[0m")
                organs = ", ".join(self.RC.ORGAN_SHORT[a] for a in report["organs"]) or self.RC.no_organ_text(report)
                lines.append(f"  Mapped organs   {organs}")
                if report["name"]: lines.append(f"\033[90m  {report['source']} / {report['name']}\033[0m")
                if report.get("ambiguous"):
                    lines.append("  \033[33m직접 고른 의미, 다음 화면에서 바꿀 수 있음\033[0m" if report["condition"] in self.RC.CHOICE else
                                 f"  \033[33m다른 의미 {len(report['readings']) - 1}개, 다음 화면에서 선택\033[0m")
                if report["model"]:
                    models = report.get("models") or []; head = "  Estimated organs" if not report["organs"] else "  Model signal"
                    if models:                                     # every model's value, the bar is the main model's
                        lines.append(head + " " * max(1, 30 - len(head)) + "".join(f"{m:>6}" for m in models))
                    else: lines.append(head)
                    for organ, score in report["estimates"]:
                        bars = round(score * 12); row = f"    {self.RC.ORGAN_SHORT[organ]:<11} \033[33m{'=' * bars}{'-' * (12 - bars)}\033[0m"
                        if models:
                            n = report["agree"].get(organ, 0)
                            vals = "".join(f"{v:6.2f}" if v > 0 else "     -" for v in report["by_model"][organ])
                            row += f"  {vals}   " + (f"{n}/{len(models)}" if n >= 2 else f"\033[90m{n}/{len(models)}\033[0m")
                        else: row += f"  {score:.2f}"
                        lines.append(row)
                lines.append("")
            wrapped = [ln for line in lines for ln in tui._wrap_ansi(line, width)]
            area = max(1, h - y0 - 3); top = max(0, min(top, len(wrapped) - area))
            for i, ln in enumerate(wrapped[top:top + area]): self.S.put_ansi(y0 + i, 2, ln)
            self.S.put(h - 2, 2, "AI process   " + self.usage.line(), self.S.dim)
            if len(wrapped) > area: self.S.put(h - 1, 2, f"{top + 1}–{min(top + area, len(wrapped))} / {len(wrapped)}", self.S.dim)
            self.scr.refresh(); key = _key(self.scr)
            if key == "UP": top = max(0, top - 1)
            elif key == "DOWN": top = min(max(0, len(wrapped) - area), top + 1)
            elif key in ("PGUP", "ESC"): return BACK
            elif key in ("PGDN", "ENTER"): return None


def run(RC, back=False):
    """-> (conditions, raw labs) or None. back: reopen at the last step (priority if it applies, else lab values), entries kept."""
    def app(scr):
        F = Form(scr, RC); st = load(); st["picked"] &= set(RC._reg); step = 0
        RC.CHOICE.update(st["choice"])
        if back:
            conds = [i for i in RC._reg if i in st["picked"]] + split_free(st["free"]); F.loading("불러오는 중 ...")
            pc = RC.patient_conditions(conds, st["raw"])
            step = 3 if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2 else 1
        while True:
            F.done = []
            if step >= 1: F.done.append(("기저질환", ", ".join([RC.condition_name(i) for i in sorted(st["picked"], key=list(RC._reg).index)] + split_free(st["free"]))))
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
                if miss and RC.HAS_LEARNED:
                    label = lambda r, a: RC.ORGAN_SHORT[a] + (f" {r['agree'][a]}/{len(r['models'])}" if r.get("models") else "")
                    estimates = [f"{r['condition']}: {', '.join(label(r, a) for a, _ in r['estimates'])}" for r in reports if r['condition'] in miss]
                    agreed = any(r.get("models") for r in reports if r["condition"] in miss)
                    k = F.choose(f"추정 장기 반영: {', '.join(miss)}", "학습 모델 추정\n" + "\n".join("  " + s for s in estimates) + "\n자동은 질환으로 인식된 입력에만 반영합니다." + ("\n모델 2개 이상이 고른 장기만 반영합니다." if agreed else ""),
                                 [n for n, _ in RC.FALLBACK_OPTS])
                    if k == BACK: step = 1; continue
                    f = RC.FALLBACK_OPTS[k][1]; RC.FALLBACK = {c: f for c in miss} if f > 0 else {}
                    F.done.append(("추정 장기", RC.FALLBACK_OPTS[k][0]))
                step = 3; st["miss"] = bool(miss)
            elif step == 3:                                       # priority between conditions on different organs
                pc = RC.patient_conditions(conds, st["raw"]); RC.PRIORITY = {}
                if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2:
                    d = RC.default_levels(pc); names = [c for c, _, _ in pc]
                    show = RC.condition_name
                    auto = "자동 우선순위\n" + "\n".join(RC.priority_lines(pc))
                    k = F.choose("질환 우선순위", auto, ["자동 / 질환 심각도 순", "직접 정하기"])
                    if k == BACK: step = 2 if st.get("miss") else 1; continue
                    if k == 1:
                        lv = F.order([show(c) for c in names], [", ".join(RC.EN[a] for a in sorted(o, key=RC.AXES.index)) for _, o, _ in pc], [d[c] for c in names])
                        if lv == BACK: continue
                        RC.PRIORITY = dict(zip(names, lv))
                return conds, st["raw"]
    return curses.wrapper(app)
