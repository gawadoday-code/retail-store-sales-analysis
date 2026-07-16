const fs = require("fs");
const vm = require("vm");

class Element {
  constructor(id) {
    this.id = id;
    this.value = "";
    this.textContent = "";
    this.children = [];
    this.listeners = {};
    this._innerHTML = "";
  }
  set innerHTML(value) {
    this._innerHTML = value;
    if (value === "") this.children = [];
  }
  get innerHTML() { return this._innerHTML; }
  appendChild(child) {
    this.children.push(child);
    if (!this.value) this.value = child.value;
  }
  addEventListener(type, handler) { this.listeners[type] = handler; }
}

const ids = [
  "rd-start", "rd-end", "rd-location", "rd-category", "rd-metric", "rd-reset",
  "rd-sales", "rd-sales-context", "rd-valid", "rd-valid-context", "rd-average",
  "rd-average-context", "rd-coverage", "rd-coverage-context", "rd-period-note",
  "rd-breakdown-note", "rd-trend", "rd-breakdown"
];
const elements = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
elements["rd-metric"].value = "salesPerTxn";
const root = new Element("retail-decision-dashboard");
root.querySelector = (selector) => elements[selector.slice(1)];
const document = {
  getElementById: (id) => id === "retail-decision-dashboard" ? root : elements[id],
  createElement: () => new Element("")
};

const html = fs.readFileSync("dashboard/index.html", "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (scripts.length !== 1) throw new Error("Expected one script block");
new vm.Script(scripts[0], { filename: "retail-dashboard.js" }).runInNewContext({
  document,
  Intl,
  Map,
  Set,
  Math,
  Number,
  String,
  Array
});

if (elements["rd-end"].value !== "2024-12") throw new Error("Partial month is not excluded by default");
if (elements["rd-sales"].textContent !== "1,526,522.5") throw new Error("Unexpected default sales total: " + elements["rd-sales"].textContent);
if (!elements["rd-trend"].innerHTML.includes("<svg")) throw new Error("Trend did not render");
if (!elements["rd-breakdown"].innerHTML.includes("<svg")) throw new Error("Breakdown did not render");

elements["rd-category"].value = "Beverages";
elements["rd-category"].listeners.change();
if (!elements["rd-breakdown"].innerHTML.includes("selected-bar")) throw new Error("Selected category is not highlighted");

elements["rd-metric"].value = "units";
elements["rd-metric"].listeners.change();
if (!elements["rd-breakdown-note"].textContent.includes("quantity coverage")) throw new Error("Quantity coverage is not shown");

elements["rd-end"].value = "2025-01";
elements["rd-end"].listeners.change();
if (!elements["rd-trend"].innerHTML.includes("partial-band")) throw new Error("Partial month is not shaded");
if (!elements["rd-period-note"].textContent.includes("partial")) throw new Error("Partial month note is missing");

elements["rd-start"].value = "2023-01";
elements["rd-end"].value = "2023-12";
elements["rd-category"].value = "All";
elements["rd-metric"].value = "salesPerTxn";
elements["rd-start"].listeners.change();
if (!elements["rd-sales-context"].textContent.includes("previous equal-length period")) throw new Error("Previous-period comparison is missing");

elements["rd-reset"].listeners.click();
if (elements["rd-end"].value !== "2024-12") throw new Error("Reset restores partial month");

console.log(JSON.stringify({
  status: "runtime-check-passed",
  defaultEnd: elements["rd-end"].value,
  sales: elements["rd-sales"].textContent,
  valid: elements["rd-valid"].textContent,
  coverage: elements["rd-coverage"].textContent,
  trendBytes: elements["rd-trend"].innerHTML.length,
  breakdownBytes: elements["rd-breakdown"].innerHTML.length
}));
