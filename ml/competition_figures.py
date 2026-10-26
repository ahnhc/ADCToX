"""Figures for the contest slides (docs/competition_plan.md): how the evidence reader decides an unseen disease (slide 5).

    ADC_RESEARCH_MODE=1 ADCTOX_LABELS=v51 ADCTOX_CACHE=<v5.1 cache> python ml/competition_figures.py
    -> docs/images/competition/evidence_example.svg
Examples are gold dev questions (not test) where x2te seed 8 changed the name-only answer; the record text is the MONDO entry
(CC BY 4.0) the reader saw, cut for space.
"""
import json, os, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P, evidence_judge as E

OUT = P.REPO + "docs/images/competition/"
EX = [("TUBERCULOSIS", "MONDO:0018076", ["infectious_immune"], ["infectious_immune", "pulmonary"]),
      ("Gluten-sensitive enteropathy", "MONDO:0005130", ["gastrointestinal", "metabolic_endocrine"], ["gastrointestinal", "infectious_immune"]),
      ("Clostridioides difficile infection", "MONDO:0000705", ["infectious_immune"], ["gastrointestinal", "infectious_immune"])]


def main():
    from xml.sax.saxutils import escape as x
    R = E.records(); os.makedirs(OUT, exist_ok=True); W, H = 1300, 760
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    for cx, t in ((20, "Input"), (300, "Linked MONDO record (what the reader sees)"), (900, "Name only"), (1100, "With the record")):
        o.append(f'<text x="{cx}" y="34" font-size="18" font-weight="bold" fill="#333">{x(t)}</text>')
    for k, (q, c, before, after) in enumerate(EX):
        y = 56 + k * 225; r = R[c]
        o.append(f'<rect x="10" y="{y}" width="{W - 20}" height="205" rx="10" fill="#f6f7f9" stroke="#d0d4da"/>')
        for n, line in enumerate(textwrap.wrap(q, 22)): o.append(f'<text x="20" y="{y + 32 + n * 22}" font-size="17" font-weight="bold" fill="#111">{x(line)}</text>')
        o.append(f'<text x="300" y="{y + 30}" font-size="14" font-weight="bold" fill="#333">{x(c + "  " + r["name"])}</text>')
        body = textwrap.wrap(E.text(r).split(" . ", 2)[-1], 82)[:7]
        for n, line in enumerate(body): o.append(f'<text x="300" y="{y + 54 + n * 20}" font-size="13" fill="#333">{x(line + (" ..." if n == len(body) - 1 else ""))}</text>')
        for cx, org, col, wt in ((900, before, "#b23b3b", "normal"), (1100, after, "#1f7a3a", "bold")):
            for n, a in enumerate(org): o.append(f'<text x="{cx}" y="{y + 32 + n * 24}" font-size="16" font-weight="{wt}" fill="{col}">{x(a)}</text>')
    o.append(f'<text x="14" y="{H - 12}" font-size="12" fill="#666">Gold dev questions; two annotators agree with the right column. Record text: MONDO (CC BY 4.0). Model: x2te seed 8, trained from scratch.</text>')
    open(OUT + "evidence_example.svg", "w", encoding="utf-8").write("\n".join(o + ["</svg>"])); print("->", OUT + "evidence_example.svg")


if __name__ == "__main__":
    main()
