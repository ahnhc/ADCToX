// A rejected fetch in boot() must reach the status line, not leave "loading…" on screen.
const fs = require("fs"), vm = require("vm");

const js = fs.readFileSync(process.argv[2], "utf8").match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
const els = {};
const el = id => els[id] || (els[id] = { textContent: "loading…", addEventListener() {} });
const ctx = {
  document: { getElementById: el, addEventListener() {} }, window: {},
  fetch: () => Promise.reject(new Error("connection reset")), console,
};
vm.createContext(ctx);
vm.runInContext(js, ctx);
setTimeout(() => {
  const status = els.status && els.status.textContent;
  if (!/connection reset/.test(status || "") || els.stamp.textContent === "loading…") {
    console.error("boot failure left the page silent: " + JSON.stringify([status, els.stamp.textContent]));
    process.exit(1);
  }
  console.log("ok");
}, 50);
