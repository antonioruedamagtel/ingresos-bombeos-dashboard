import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(new URL("../docs/app.js", import.meta.url), "utf8");
const snapshot = JSON.parse(fs.readFileSync(new URL("../docs/data/demo-data.json", import.meta.url), "utf8"));
const context = vm.createContext({
  console,
  window: { addEventListener() {}, dispatchEvent() {} },
  document: { querySelector() {}, querySelectorAll() { return []; } },
  history: { replaceState() {} },
  location: { hash: "" },
  Intl, Date, Blob, URL, setTimeout, clearTimeout,
});
vm.runInContext(source, context, { filename: "app.js" });
context.__snapshot = snapshot;
const result = vm.runInContext(`
  DATA = __snapshot;
  state.start = DATA.metadata.period_start.slice(0, 7);
  state.end = DATA.metadata.period_end.slice(0, 7);
  forecastScenario(1, {
    pT: 500, pP: 500, useful: 4000, effT: .90, effP: .87,
    availability: .95, cycles: 220, variableOpex: 2.5,
    fixedOpex: 12000, ancillary: .12
  });
`, context);

for (const field of ["net", "annualGeneration", "buy", "sell", "cycleMargin"]) {
  if (!Number.isFinite(result[field])) throw new Error(`Forecast ${field} is not finite`);
}
if (result.availableDays <= 0) throw new Error("Forecast did not use any price day");
if (result.sell < result.buy) throw new Error("Dispatch selected a sell price below the buy price");
console.log(JSON.stringify({ status: "OK", availableDays: result.availableDays, net: Math.round(result.net) }));
