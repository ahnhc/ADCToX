// Exercises web/index.html's axisRow against the two band bases.
//
// The UI had no tests. That was tolerable while every axis was rendered the same way; it
// stopped being tolerable once the band basis started changing which number is primary and
// what the bar is scaled to. The scale is the part worth guarding: a 3% serious rate drawn
// on the common table's 0-60% axis is an empty bar beside a red "high" badge, which reads
// as a bug and costs exactly the trust the number needs.
const fs = require("fs"), vm = require("vm"), path = require("path");

const page = path.join(__dirname, "..", "..", "web", "index.html");
const js = fs.readFileSync(page, "utf8").match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
const ctx = {
  document: { getElementById: () => null, querySelectorAll: () => [], addEventListener() {} },
  window: {}, fetch: () => Promise.resolve({ json: () => ({}) }), console,
};
vm.createContext(ctx);
try { vm.runInContext(js, ctx); } catch (e) { /* boot() needs a DOM; the functions are defined */ }

const axisRow = ctx.axisRow;
if (typeof axisRow !== "function") { console.error("axisRow not defined"); process.exit(1); }

const base = {
  organ_axis: "pulmonary", label: "Pulmonary",
  point_estimate: 0.1402, serious_estimate: 0.0313,
  interval: { lo: 0.09, hi: 0.19 },
  serious_interval: { lo: 0.0092, hi: 0.0759 },
  risk_band: "high", band_source: "model",
  weight_applied: 3.0, n_supporting_agents: 4, n_supporting_arms: 67, drivers: [],
};
const serious = { ...base, band_basis: "serious", at_risk_for_patient: true };
const common = {
  ...base, organ_axis: "gastrointestinal", label: "Gastrointestinal",
  band_basis: "common", at_risk_for_patient: false,
  point_estimate: 0.5948, serious_estimate: 0.0336,
};
const noEv = { ...serious, risk_band: "no_evidence", n_supporting_arms: 1,
               serious_estimate: null, point_estimate: null,
               serious_interval: null, interval: null };

const a = axisRow(serious), b = axisRow(common), c = axisRow(noEv);
const barPos = (html) => {
  const m = html.match(/class="pt" style="left:([\d.]+)%/);
  return m ? parseFloat(m[1]) : null;
};

// pct() is toPrecision(2) -- two significant figures, per the project's uncertainty rules.
const checks = [
  ["serious basis makes the serious rate primary", a.includes("3.1%")],
  ["serious basis is labelled on the row", a.includes("serious-event basis")],
  ["serious basis shows the any-grade rate as secondary", a.includes("any-grade 14%")],
  ["serious basis shows ITS OWN interval, not the any-grade one",
   a.includes("0.92%") && !a.includes("[9.0%")],
  ["common basis makes the any-grade rate primary", b.includes("59%")],
  ["common basis shows the serious rate as secondary", b.includes("serious 3.4%")],
  ["common basis carries no basis label", !b.includes("serious-event basis")],
  ["no-evidence renders hatched, not as a low bar", c.includes("hatch")],
  ["no-evidence shows no number", !c.includes("%</span>")],
  // The scale follows the basis: 3.13 on an 8% axis lands near 39%, not near 5%.
  ["serious bar is scaled to the serious range", (() => {
    const p = barPos(a); return p !== null && p > 30 && p < 50;
  })()],
  ["common bar is scaled to the common range", (() => {
    const p = barPos(b); return p !== null && p > 90 && p <= 100;
  })()],
];

let failed = 0;
for (const [name, ok] of checks) {
  if (!ok) { failed++; console.error("FAIL  " + name); } else { console.log("ok    " + name); }
}
process.exit(failed ? 1 : 0);
