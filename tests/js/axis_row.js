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


// --- the evidence table -----------------------------------------------------------
// Mixed metrics in one column is how a winning result reads as a loss.
const evalRow = ctx.evalRow;
if (typeof evalRow !== "function") { console.error("evalRow not defined"); process.exit(1); }
const rank = evalRow({
  name: "anticipating a dated FDA label change", direction: "lower_is_better",
  metric: "predicted rank of the organ", model: 4.6667, best_baseline: 7.5,
  verdict: "beats the null but p = 0.515",
});
const auc = evalRow({
  name: "within-arm axis ranking", direction: "higher_is_better",
  metric: "AUROC", model: 0.827, best_baseline: 0.8437, delta: -0.012,
  verdict: "includes zero",
});
const count = evalRow({
  name: "label-rule layer", direction: "count",
  metric: "rules whose removal changes the band", model: 3, n_flags: 5,
  verdict: "3 of 5 load-bearing",
});
const more = [
  ["a rank metric says lower is better", rank.includes("lower is better")],
  ["an AUROC says higher is better", auc.includes("higher is better")],
  ["a count is not formatted as a score", !count.includes("3.000")],
  ["a count shows its denominator", count.includes("3 of 5")],
  ["a count claims no direction", !count.includes("better")],
];
for (const [name, ok] of more) {
  if (!ok) { failed++; console.error("FAIL  " + name); } else { console.log("ok    " + name); }
}


// --- driver panel ---------------------------------------------------------------------
// The plan asks for the four declared driver sources to be separated by colour, because the
// first question a reader has about a red organ is whether the model said so or a rule did.
// `elicited_prior` is the source with no training data behind it, so it must never render
// as a fitted quantity.
const withDrivers = {
  organ_axis: "pulmonary", label: "Pulmonary", risk_band: "high",
  band_basis: "serious", band_source: "rule",
  point_estimate: 0.14, serious_estimate: 0.03,
  interval: { lo: 0.1, hi: 0.19 }, serious_interval: { lo: 0.01, hi: 0.06 },
  n_supporting_arms: 40, n_supporting_agents: 5,
  at_risk_for_patient: true, weight_applied: 3.0,
  drivers: [
    { factor: "axis baseline", source: "model", contribution: -1.8089 },
    { factor: "payload chemistry (camptothecin, topo1)", source: "model",
      contribution: -0.0425 },
    { factor: "label rule: dxd_prior_ild", source: "rule", contribution: null,
      detail: "ENHERTU boxed warning" },
    { factor: "comorbidity weighting on pulmonary", source: "elicited_prior",
      contribution: 3.0 },
  ],
};
const drvHtml = axisRow(withDrivers);
const bareHtml = axisRow({ ...withDrivers, drivers: [] });

const driverChecks = [
  ["a why toggle appears when drivers exist",
    drvHtml.includes('data-why="why-pulmonary"')],
  ["the panel starts hidden", /id="why-pulmonary"[^>]*hidden/.test(drvHtml)],
  ["every driver source is colour-tagged",
    ["model", "rule", "elicited_prior"].every(
      (src) => drvHtml.includes("var(--src-" + src + ")"))],
  ["a fitted contribution shows its number", drvHtml.includes("-1.809")],
  ["a rule shows a dash rather than a number", drvHtml.includes("&mdash;")],
  ["the elicited prior is not coloured as the model",
    drvHtml.includes("elicited prior") &&
    !drvHtml.includes('var(--src-model)">elicited')],
  ["no toggle when there is nothing to explain", !bareHtml.includes("data-why")],
  ["no empty panel when there is nothing to explain",
    !bareHtml.includes('class="why"')],
];
for (const [name, ok] of driverChecks) {
  if (!ok) { failed++; console.error("FAIL  " + name); } else { console.log("ok    " + name); }
}

// --- the evidence meter counts agents, not arms ---
//
// It counted arms, which is the quantity this project's central structural finding says not
// to count: design features are agent-level constants, so 67 arms of 2 agents are two
// observations of that chemistry. An axis with arms to spare and two agents was shown as
// well-evidenced. Measured consequence: otologic rests on 18 of the corpus's 65 agents
// where haematologic rests on 59, and it is not short of arms. Negative results 5 and 49.
const manyArmsFewAgents = { ...withDrivers, n_supporting_arms: 67, n_supporting_agents: 2,
  risk_band: "high", drivers: [] };
const fewArmsManyAgents = { ...withDrivers, n_supporting_arms: 2, n_supporting_agents: 9,
  risk_band: "high", drivers: [] };
const thinChecks = [
  ["many arms over two agents is thin",
    /class="ev thin"/.test(axisRow(manyArmsFewAgents))],
  ["two arms over nine agents is not thin",
    /class="ev "/.test(axisRow(fewArmsManyAgents))],
  ["the thin tooltip says how many agents, not just that it is thin",
    axisRow(manyArmsFewAgents).includes("2 agents of this payload chemistry")],
  ["the thin tooltip still refuses to read as low risk",
    axisRow(manyArmsFewAgents).includes("Not the same as low risk")],
  ["a well-evidenced row reports both counts",
    axisRow(fewArmsManyAgents).includes("2 arms across 9 agents")],
];
for (const [name, ok] of thinChecks) {
  if (!ok) { failed++; console.error("FAIL  " + name); } else { console.log("ok    " + name); }
}

process.exit(failed ? 1 : 0);
