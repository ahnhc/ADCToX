"""draw ADCToX as shapes on a fine pixel grid, render as braille (2x4 dots per cell)."""
import math, re, sys
H = 20                                   # pixel rows (5 text lines x 4)
def canvas(w): return [[None] * w for _ in range(H)]
def put(g, x, y, c):
    if 0 <= y < H and 0 <= x < len(g[0]): g[y][x] = c
def line(g, x0, y0, x1, y1, c, t=1.0):
    n = int(max(abs(x1 - x0), abs(y1 - y0)) * 3) + 1
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n; y = y0 + (y1 - y0) * i / n
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if math.hypot(dx, dy) <= t: put(g, round(x + dx), round(y + dy), c)
def disc(g, cx, cy, r, c):
    for y in range(H):
        for x in range(len(g[0])):
            if math.hypot(x - cx, y - cy) <= r: put(g, x, y, c)
def fill(g, pred, c):
    for y in range(H):
        for x in range(len(g[0])):
            if pred(x, y): put(g, x, y, c)

def letter_A():                          # Erlenmeyer flask: rim, neck, sloped body, drug inside, bubbles
    w = 22; g = canvas(w)
    line(g, 7, 0, 14, 0, "c", 1.0)                       # rim
    line(g, 9, 1, 9, 6, "c", 0.8); line(g, 12, 1, 12, 6, "c", 0.8)   # neck
    line(g, 9, 6, 1, 18, "c", 0.9); line(g, 12, 6, 20, 18, "c", 0.9)  # shoulders
    line(g, 1, 19, 20, 19, "c", 0.9)                     # base
    def inside(x, y):
        if y < 11 or y > 18: return False
        half = 1.5 + (y - 6) * (8 / 12)
        return abs(x - 10.5) < half - 0.6
    fill(g, inside, "y")
    for bx, by in ((8, 13), (12, 15), (10, 17)): put(g, bx, by, None)   # bubbles
    return g
def letter_D():
    w = 17; g = canvas(w)
    line(g, 1, 0, 1, 19, "c", 1.3)
    for a in range(0, 181, 3):
        t = math.radians(a - 90); line(g, 1 + 14 * math.cos(t), 9.5 + 9.5 * math.sin(t), 1 + 14 * math.cos(t), 9.5 + 9.5 * math.sin(t), "c", 1.3)
    line(g, 1, 0, 6, 0, "c", 1.0); line(g, 1, 19, 6, 19, "c", 1.0)
    return g
def letter_C():
    w = 16; g = canvas(w)
    for a in range(40, 321, 3):
        t = math.radians(a); line(g, 9 + 8.5 * math.cos(t), 9.5 - 9.5 * math.sin(t), 9 + 8.5 * math.cos(t), 9.5 - 9.5 * math.sin(t), "c", 1.3)
    return g
def letter_T():                          # syringe: thumb press, plunger, barrel with drug and marks, needle
    w = 17; g = canvas(w)
    line(g, 0, 0, 16, 0, "r", 1.0)                       # thumb press = T bar
    line(g, 8, 1, 8, 4, "r", 0.5)                        # plunger rod
    line(g, 4, 5, 12, 5, "r", 0.5)                       # flange
    line(g, 5, 5, 5, 15, "r", 0.8); line(g, 11, 5, 11, 15, "r", 0.8); line(g, 5, 15, 11, 15, "r", 0.8)
    fill(g, lambda x, y: 6 <= x <= 10 and 9 <= y <= 14, "y")
    for my in (7, 9, 11, 13): put(g, 11, my, "r"); put(g, 12, my, "r")   # marks
    line(g, 8, 16, 8, 19, "r", 0.4)                      # needle
    return g
def letter_o():                          # toxic drop
    w = 14; g = canvas(w)
    def drop(x, y):
        cy, r = 14.0, 5.5
        if y >= cy - 1: return math.hypot(x - 6.5, y - cy) <= r
        top = 4
        if y < top: return False
        half = r * (y - top) / (cy - 1 - top) ** 1.0 * 0.95
        return abs(x - 6.5) <= half
    fill(g, drop, "r")
    put(g, 4, 12, None); put(g, 4, 13, None); put(g, 5, 11, None)          # highlight
    return g
def letter_X():                          # crossed bones with knobbed ends
    w = 22; g = canvas(w)
    line(g, 3, 2, 18, 17, "r", 1.0); line(g, 18, 2, 3, 17, "r", 1.0)
    for (cx, cy) in ((3, 2), (18, 17), (18, 2), (3, 17)):
        ox = -1 if cx < 10 else 1; oy = -1 if cy < 10 else 1
        disc(g, cx + ox * 1.3, cy, 1.8, "r"); disc(g, cx, cy + oy * 1.3, 1.8, "r")
    return g
LETTERS = [letter_A, letter_D, letter_C, letter_T, letter_o, letter_X]
COL = {"c": "36", "y": "33", "r": "31"}
def render(gap=3, color=True):
    gs = [f() for f in LETTERS]; W = sum(len(g[0]) for g in gs) + gap * (len(gs) - 1)
    big = canvas(W); x0 = 0
    for g in gs:
        for y in range(H):
            for x in range(len(g[0])):
                if g[y][x]: big[y][x0 + x] = g[y][x]
        x0 += len(g[0]) + gap
    if W % 2: [row.append(None) for row in big]; W += 1
    bits = [(0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80)]
    out = []
    for cy in range(0, H, 4):
        s = ""
        for cx in range(0, W, 2):
            v = 0; cols = {}
            for dx, dy, b in bits:
                c = big[cy + dy][cx + dx]
                if c: v |= b; cols[c] = cols.get(c, 0) + 1
            if not v: s += " "; continue
            c = "y" if "y" in cols and cols["y"] >= max(cols.values()) else max(cols, key=cols.get)
            ch = chr(0x2800 + v); s += f"\033[{COL[c]};1m{ch}\033[0m" if color else ch
        out.append(s.rstrip())
    return out
if __name__ == "__main__":
    o = render(color="--plain" not in sys.argv); print("\n".join(o)); print(max(len(re.sub(r'\x1b\[[\d;]*m', '', l)) for l in o))
