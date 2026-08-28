"use strict";

const COLORS = {
  navy: "#0b1f3a", blue: "#1261a6", teal: "#00a7a0", purple: "#7251c8",
  orange: "#eb8b32", red: "#d95f59", cyan: "#38a3c5", grey: "#8795a5"
};
const PALETTE = [COLORS.teal, COLORS.blue, COLORS.purple, COLORS.orange, COLORS.cyan, "#45a86f", "#cc6f9b", COLORS.grey];
const MARKET_DESCRIPTIONS = {
  "Mercado diario": "Energía P48 valorada al precio marginal diario.",
  "Intradiario": "Cambios de programa en subastas y negociación continua.",
  "Restricciones diario": "Resolución de restricciones y reequilibrio previo.",
  "Restricciones tiempo real": "Energía de restricciones y desvíos en operación.",
  "RR": "Reserva de reemplazo activada.",
  "mFRR": "Reserva manual de recuperación de frecuencia.",
  "aFRR banda": "Disponibilidad de banda secundaria.",
  "aFRR energia": "Estimación de energía secundaria activada."
};

let DATA;
const state = { asset: "ALL", start: "", end: "", metric: "EUR" };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const sum = (rows, field) => rows.reduce((acc, row) => acc + (Number(row[field]) || 0), 0);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const formatNumber = (value, digits = 0) => new Intl.NumberFormat("es-ES", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value) || 0);
const formatCompact = (value) => new Intl.NumberFormat("es-ES", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value) || 0);
const formatDate = (iso) => new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(`${iso}T12:00:00`));
const formatMonth = (month) => new Intl.DateTimeFormat("es-ES", { month: "short", year: "numeric" }).format(new Date(`${month}-01T12:00:00`));

function groupSum(rows, key, field) {
  const result = new Map();
  rows.forEach(row => result.set(row[key], (result.get(row[key]) || 0) + (Number(row[field]) || 0)));
  return result;
}

function plot(element, traces, layout = {}) {
  const base = {
    margin: { l: 58, r: 20, t: 22, b: 48 }, paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)", font: { family: "Inter, Segoe UI, sans-serif", size: 11, color: "#647287" },
    hoverlabel: { bgcolor: COLORS.navy, bordercolor: COLORS.navy, font: { color: "white" } },
    xaxis: { gridcolor: "#edf1f4", zerolinecolor: "#cbd6e1", automargin: true },
    yaxis: { gridcolor: "#edf1f4", zerolinecolor: "#cbd6e1", automargin: true },
    legend: { orientation: "h", y: 1.13, x: 0 }
  };
  const merged = { ...base, ...layout, xaxis: { ...base.xaxis, ...(layout.xaxis || {}) }, yaxis: { ...base.yaxis, ...(layout.yaxis || {}) } };
  return Plotly.react(element, traces, merged, { responsive: true, displayModeBar: false, locale: "es" });
}

function currentRows() {
  return DATA.monthly.filter(row => (state.asset === "ALL" || row.asset === state.asset) && row.month >= state.start && row.month <= state.end);
}

function currentAssets() {
  return DATA.assets.filter(asset => state.asset === "ALL" || asset.asset === state.asset);
}

function selectedMonths() {
  return [...new Set(currentRows().map(row => row.month))].sort();
}

function metricValue(revenue, mw, monthCount = selectedMonths().length, monthlyPoint = false) {
  if (state.metric === "EUR") return revenue;
  if (!mw) return 0;
  if (state.metric === "EUR_MW") return revenue / mw;
  return revenue / mw * (monthlyPoint ? 12 : 12 / Math.max(monthCount, 1));
}

function metricLabel() {
  return { EUR: "EUR", EUR_MW: "EUR/MW", EUR_MW_YEAR: "EUR/MW-año" }[state.metric];
}

function formatMetric(value) {
  return state.metric === "EUR" ? `${formatCompact(value)} €` : `${formatNumber(value, 0)} ${metricLabel()}`;
}

function plantMw(name) {
  return Number(DATA.assets.find(asset => asset.asset === name)?.mw_reference) || 0;
}

function totalSelectedMw() {
  return sum(currentAssets(), "mw_reference");
}

function calculatedCaptured(rows, role) {
  const energyRows = rows.filter(row => row.market !== "AFRR_BANDA" && row.role === role);
  const revenue = groupSum(energyRows, "asset", "revenue");
  const p48 = groupSum(rows.filter(row => row.market === "DA" && row.role === role), "asset", "quantity");
  return currentAssets().map(asset => ({
    asset: asset.asset,
    p48: p48.get(asset.asset) || 0,
    revenue: revenue.get(asset.asset) || 0,
    price: (revenue.get(asset.asset) || 0) / ((p48.get(asset.asset) || 0) || NaN)
  }));
}

function kpiCard(label, value, note, accent, icon) {
  return `<article class="kpi-card" style="--accent:${accent}"><small>${escapeHtml(label)}<span class="mini-icon">${icon}</span></small><strong>${escapeHtml(value)}</strong><p>${escapeHtml(note)}</p></article>`;
}

function renderSummary() {
  const rows = currentRows();
  const months = selectedMonths();
  const mw = totalSelectedMw();
  const revenue = sum(rows, "revenue");
  const da = rows.filter(row => row.market === "DA");
  const generation = sum(da.filter(row => row.role === "generation"), "quantity");
  const pumping = Math.abs(sum(da.filter(row => row.role === "pumping"), "quantity"));
  const observed = 100 * sum(rows, "observed_rows") / Math.max(sum(rows, "rows"), 1);
  const marketCount = new Set(rows.filter(row => Math.abs(Number(row.revenue)) > 0).map(row => row.market_group)).size;

  $("#selection-label").textContent = `${state.asset === "ALL" ? "8 centrales" : state.asset} · ${formatMonth(state.start)} – ${formatMonth(state.end)}`;
  $("#summary-kpis").innerHTML = [
    kpiCard("Ingreso incremental", formatMetric(metricValue(revenue, mw)), `${formatNumber(revenue, 0)} EUR acumulados`, COLORS.teal, "€"),
    kpiCard("Generación P48", `${formatCompact(generation)} MWh`, "Mercado diario", COLORS.blue, "↗"),
    kpiCard("Bombeo P48", `${formatCompact(pumping)} MWh`, "Consumo en valor absoluto", COLORS.purple, "↘"),
    kpiCard("Dato observado", `${formatNumber(observed, 1)} %`, `${marketCount} familias de mercado con valor`, COLORS.orange, "✓")
  ].join("");

  const monthlyRevenue = groupSum(rows, "month", "revenue");
  const trendX = months;
  const trendY = months.map(month => metricValue(monthlyRevenue.get(month) || 0, mw, 1, true));
  plot("trend-chart", [{ type: "scatter", mode: "lines+markers", x: trendX, y: trendY, line: { color: COLORS.teal, width: 3 }, marker: { size: 6, color: COLORS.navy }, fill: "tozeroy", fillcolor: "rgba(0,167,160,.09)", hovertemplate: `%{x}<br><b>%{y:,.0f} ${metricLabel()}</b><extra></extra>` }], { yaxis: { tickformat: ",.2s", title: metricLabel() }, xaxis: { type: "category" } });

  const marketMap = groupSum(rows, "market_group", "revenue");
  const markets = [...marketMap.entries()].filter(([, value]) => Math.abs(value) > .01).sort((a, b) => a[1] - b[1]);
  plot("market-mix-chart", [{ type: "bar", orientation: "h", y: markets.map(item => item[0]), x: markets.map(item => metricValue(item[1], mw)), marker: { color: markets.map((_, index) => PALETTE[index % PALETTE.length]) }, hovertemplate: `<b>%{y}</b><br>%{x:,.0f} ${metricLabel()}<extra></extra>` }], { showlegend: false, margin: { l: 145, r: 18, t: 16, b: 38 }, xaxis: { tickformat: ",.2s", title: metricLabel() } });

  const assetMap = groupSum(rows, "asset", "revenue");
  const assetValues = currentAssets().map(asset => ({ name: asset.asset, value: metricValue(assetMap.get(asset.asset) || 0, Number(asset.mw_reference)) })).sort((a, b) => a.value - b.value);
  plot("asset-chart", [{ type: "bar", orientation: "h", y: assetValues.map(item => item.name), x: assetValues.map(item => item.value), marker: { color: COLORS.blue }, hovertemplate: `<b>%{y}</b><br>%{x:,.0f} ${metricLabel()}<extra></extra>` }], { showlegend: false, margin: { l: 125, r: 18, t: 16, b: 38 }, xaxis: { tickformat: ",.2s", title: metricLabel() } });

  renderAssetTable(rows);
}

function tableAssetRows(rows) {
  const revenue = groupSum(rows, "asset", "revenue");
  const generation = groupSum(rows.filter(row => row.market === "DA" && row.role === "generation"), "asset", "quantity");
  const pumping = groupSum(rows.filter(row => row.market === "DA" && row.role === "pumping"), "asset", "quantity");
  const captured = new Map(calculatedCaptured(rows, "generation").map(row => [row.asset, row.price]));
  return currentAssets().map(asset => {
    const assetRows = rows.filter(row => row.asset === asset.asset);
    return {
      asset: asset.asset, operator: asset.operator, mw: Number(asset.mw_reference),
      revenue: revenue.get(asset.asset) || 0, generation: generation.get(asset.asset) || 0,
      pumping: Math.abs(pumping.get(asset.asset) || 0), captured: captured.get(asset.asset),
      observed: 100 * sum(assetRows, "observed_rows") / Math.max(sum(assetRows, "rows"), 1)
    };
  }).sort((a, b) => b.revenue - a.revenue);
}

function renderAssetTable(rows) {
  $("#asset-table").innerHTML = tableAssetRows(rows).map((row, index) => `<tr>
    <td><span class="asset-name"><span class="asset-dot" style="background:${PALETTE[index % PALETTE.length]}"></span>${escapeHtml(row.asset)}</span></td>
    <td>${escapeHtml(row.operator)}</td><td class="num">${formatNumber(row.mw, 1)}</td>
    <td class="num"><strong>${formatNumber(row.revenue, 0)} €</strong></td>
    <td class="num">${formatNumber(row.generation, 0)}</td><td class="num">${formatNumber(row.pumping, 0)}</td>
    <td class="num">${Number.isFinite(row.captured) ? formatNumber(row.captured, 2) : "—"}</td>
    <td class="num"><span class="quality-pill ${row.observed < 95 ? "warn" : ""}">${formatNumber(row.observed, 1)} %</span></td>
  </tr>`).join("");
}

function renderPlants() {
  const rows = currentRows();
  const revenue = groupSum(rows, "asset", "revenue");
  const generation = new Map(calculatedCaptured(rows, "generation").map(row => [row.asset, row.price]));
  $("#plant-cards").innerHTML = currentAssets().map(asset => `<article class="plant-card"><header><div><h3>${escapeHtml(asset.asset)}</h3><span class="operator">${escapeHtml(asset.operator)}</span></div><span class="mw">${formatNumber(asset.mw_reference, 0)} MW</span></header><dl><dt>Ubicación</dt><dd>${escapeHtml(asset.provincia)}</dd><dt>Ingreso periodo</dt><dd>${formatCompact(revenue.get(asset.asset) || 0)} €</dd><dt>Precio capturado gen.</dt><dd>${Number.isFinite(generation.get(asset.asset)) ? `${formatNumber(generation.get(asset.asset), 1)} €/MWh` : "—"}</dd></dl></article>`).join("");
  renderCapturedChart("captured-generation-chart", calculatedCaptured(rows, "generation"), COLORS.teal);
  renderCapturedChart("captured-pumping-chart", calculatedCaptured(rows, "pumping"), COLORS.purple);
}

function renderCapturedChart(element, rows, color) {
  const valid = rows.filter(row => Number.isFinite(row.price)).sort((a, b) => a.price - b.price);
  plot(element, [{ type: "bar", orientation: "h", y: valid.map(row => row.asset), x: valid.map(row => row.price), marker: { color }, hovertemplate: "<b>%{y}</b><br>%{x:,.2f} €/MWh<extra></extra>" }], { showlegend: false, margin: { l: 130, r: 20, t: 18, b: 42 }, xaxis: { title: "€/MWh" } });
}

function renderEnergy() {
  const rows = currentRows().filter(row => row.market === "DA");
  const genRows = rows.filter(row => row.role === "generation");
  const pumpRows = rows.filter(row => row.role === "pumping");
  const generation = sum(genRows, "quantity");
  const pumping = Math.abs(sum(pumpRows, "quantity"));
  const ratio = generation / (pumping || NaN);
  $("#energy-kpis").innerHTML = [
    kpiCard("Generación", `${formatCompact(generation)} MWh`, "Volumen P48", COLORS.teal, "↗"),
    kpiCard("Bombeo", `${formatCompact(pumping)} MWh`, "Volumen P48 absoluto", COLORS.purple, "↘"),
    kpiCard("Ratio salida/entrada", Number.isFinite(ratio) ? formatNumber(ratio, 2) : "—", "No equivale a eficiencia técnica", COLORS.orange, "÷")
  ].join("");
  const months = selectedMonths();
  const gen = groupSum(genRows, "month", "quantity");
  const pump = groupSum(pumpRows, "month", "quantity");
  plot("energy-chart", [
    { type: "bar", name: "Generación", x: months, y: months.map(month => gen.get(month) || 0), marker: { color: COLORS.teal }, hovertemplate: "%{x}<br>%{y:,.0f} MWh<extra>Generación</extra>" },
    { type: "bar", name: "Bombeo", x: months, y: months.map(month => -Math.abs(pump.get(month) || 0)), marker: { color: COLORS.purple }, hovertemplate: "%{x}<br>%{customdata:,.0f} MWh<extra>Bombeo</extra>", customdata: months.map(month => Math.abs(pump.get(month) || 0)) }
  ], { barmode: "relative", yaxis: { title: "MWh", tickformat: ",.2s" }, xaxis: { type: "category" } });
}

function pricesInSelection() {
  return DATA.prices.filter(row => row.datetime.slice(0, 7) >= state.start && row.datetime.slice(0, 7) <= state.end);
}

function renderMarkets() {
  const rows = currentRows();
  const mw = totalSelectedMw();
  const groups = groupSum(rows, "market_group", "revenue");
  const sorted = [...groups.entries()].sort((a, b) => b[1] - a[1]);
  plot("markets-chart", [{ type: "bar", x: sorted.map(item => item[0]), y: sorted.map(item => metricValue(item[1], mw)), marker: { color: sorted.map((_, i) => PALETTE[i % PALETTE.length]) }, hovertemplate: `<b>%{x}</b><br>%{y:,.0f} ${metricLabel()}<extra></extra>` }], { showlegend: false, margin: { l: 62, r: 15, t: 20, b: 120 }, xaxis: { tickangle: -32 }, yaxis: { title: metricLabel(), tickformat: ",.2s" } });

  const daily = new Map();
  pricesInSelection().forEach(row => {
    const day = row.datetime.slice(0, 10);
    const current = daily.get(day) || { total: 0, n: 0 };
    current.total += Number(row.price) || 0; current.n += 1; daily.set(day, current);
  });
  const days = [...daily.keys()].sort();
  plot("price-chart", [{ type: "scatter", mode: "lines", x: days, y: days.map(day => daily.get(day).total / daily.get(day).n), line: { color: COLORS.orange, width: 1.7 }, fill: "tozeroy", fillcolor: "rgba(235,139,50,.10)", hovertemplate: "%{x}<br><b>%{y:,.2f} €/MWh</b><extra></extra>" }], { showlegend: false, yaxis: { title: "€/MWh" } });
  $("#market-legend").innerHTML = DATA.market_groups.map((name, index) => `<div class="legend-item"><strong><span class="asset-dot" style="display:inline-block;background:${PALETTE[index % PALETTE.length]}"></span> ${escapeHtml(name)}</strong><p>${escapeHtml(MARKET_DESCRIPTIONS[name] || "Componente incluido en la reconciliación incremental.")}</p></div>`).join("");
}

function renderQuality() {
  const rows = currentRows();
  const observed = 100 * sum(rows, "observed_rows") / Math.max(sum(rows, "rows"), 1);
  const coverage = DATA.coverage;
  const avgCoverage = sum(coverage, "cobertura_precio_pct") / Math.max(coverage.length, 1);
  const closed = DATA.reconciliation.filter(row => row.closes === true || row.closes === 1).length;
  $("#quality-kpis").innerHTML = [
    kpiCard("Filas observadas", `${formatNumber(observed, 2)} %`, "Resto identificado como estimado", COLORS.teal, "✓"),
    kpiCard("Cobertura de precio", `${formatNumber(avgCoverage, 1)} %`, "Promedio por mercado", COLORS.blue, "◫"),
    kpiCard("Cierres de volumen", `${closed}/${DATA.reconciliation.length}`, "Activo y rol", closed === DATA.reconciliation.length ? COLORS.teal : COLORS.orange, "≋")
  ].join("");
  const sorted = [...coverage].sort((a, b) => Number(a.cobertura_precio_pct) - Number(b.cobertura_precio_pct));
  plot("coverage-chart", [{ type: "bar", orientation: "h", y: sorted.map(row => row.market), x: sorted.map(row => Number(row.cobertura_precio_pct)), marker: { color: sorted.map(row => Number(row.cobertura_precio_pct) >= 95 ? COLORS.teal : COLORS.orange) }, hovertemplate: "<b>%{y}</b><br>%{x:,.1f} %<extra></extra>" }], { showlegend: false, margin: { l: 118, r: 18, t: 18, b: 42 }, xaxis: { range: [0, 105], title: "%" } });
  $("#quality-table").innerHTML = DATA.reconciliation.map(row => {
    const closes = row.closes === true || row.closes === 1;
    return `<tr><td>${escapeHtml(row.entity)}</td><td>${row.role === "generation" ? "Generación" : "Bombeo"}</td><td class="num">${formatNumber(row.p48, 1)}</td><td class="num">${formatNumber(row.residual, 3)}</td><td class="num">${formatNumber(100 * Number(row.residual_pct || 0), 5)}</td><td><span class="quality-pill ${closes ? "" : "warn"}">${closes ? "CIERRA" : "REVISAR"}</span></td></tr>`;
  }).join("");
}

function toggleStorageMode() {
  const reservoir = $("#storage-mode").value === "reservoir";
  $("#mwh-fields").classList.toggle("is-disabled", reservoir);
  $("#mwh-fields").setAttribute("aria-disabled", String(reservoir));
  $("#useful-mwh").disabled = reservoir;
  $("#reservoir-fields").classList.toggle("is-disabled", !reservoir);
  $("#reservoir-fields").setAttribute("aria-disabled", String(!reservoir));
  $("#volume-hm3").disabled = !reservoir;
  $("#head-m").disabled = !reservoir;
  calculateForecast();
}

function weightedDispatch(items, targetEnergy, power, ascending, excluded = new Set()) {
  const ordered = items.map((item, index) => ({ ...item, index })).filter(item => !excluded.has(item.index)).sort((a, b) => ascending ? a.price - b.price : b.price - a.price);
  let remaining = targetEnergy, value = 0, energy = 0;
  const used = new Set();
  for (const item of ordered) {
    if (remaining <= 1e-8) break;
    const amount = Math.min(power, remaining);
    value += item.price * amount; energy += amount; remaining -= amount; used.add(item.index);
  }
  return { value, energy, used };
}

function forecastScenario(multiplier, inputs) {
  const byDay = new Map();
  pricesInSelection().forEach(row => {
    const day = row.datetime.slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push({ price: Number(row.price) * multiplier });
  });
  const cycles = [];
  byDay.forEach(items => {
    if (items.length < 8) return;
    const pumpNeeded = inputs.useful / (inputs.effT * inputs.effP);
    const scale = Math.min(1, items.length / (inputs.useful / inputs.pT + pumpNeeded / inputs.pP));
    const genTarget = inputs.useful * scale;
    const pumpTarget = pumpNeeded * scale;
    const pumped = weightedDispatch(items, pumpTarget, inputs.pP, true);
    const generated = weightedDispatch(items, genTarget, inputs.pT, false, pumped.used);
    if (pumped.energy > 0 && generated.energy > 0) cycles.push({ margin: generated.value - pumped.value, generated: generated.energy, pumped: pumped.energy, buy: pumped.value / pumped.energy, sell: generated.value / generated.energy });
  });
  const average = field => cycles.reduce((acc, row) => acc + row[field], 0) / Math.max(cycles.length, 1);
  const activeCycles = inputs.cycles * inputs.availability;
  const energyMargin = average("margin") * activeCycles;
  const ancillary = Math.max(0, energyMargin) * inputs.ancillary;
  const variableOpex = average("generated") * activeCycles * inputs.variableOpex;
  const fixedOpex = inputs.fixedOpex * inputs.pT;
  return {
    net: energyMargin + ancillary - variableOpex - fixedOpex,
    energyMargin, ancillary, variableOpex, fixedOpex,
    annualGeneration: average("generated") * activeCycles,
    buy: average("buy"), sell: average("sell"),
    cycleMargin: average("margin"), availableDays: cycles.length,
    dailyGeneration: average("generated"), dailyPumping: average("pumped")
  };
}

function readForecastInputs() {
  const effT = Number($("#eff-t").value) / 100;
  const effP = Number($("#eff-p").value) / 100;
  const useful = $("#storage-mode").value === "mwh"
    ? Number($("#useful-mwh").value)
    : 2.725 * Number($("#volume-hm3").value) * Number($("#head-m").value) * effT;
  return {
    pT: Math.max(Number($("#p-turbine").value), 1), pP: Math.max(Number($("#p-pump").value), 1), useful: Math.max(useful, 1),
    effT: Math.min(Math.max(effT, .01), 1), effP: Math.min(Math.max(effP, .01), 1),
    availability: Math.min(Math.max(Number($("#availability").value) / 100, .01), 1),
    cycles: Math.min(Math.max(Number($("#cycles").value), 1), 365),
    variableOpex: Math.max(Number($("#variable-opex").value), 0), fixedOpex: Math.max(Number($("#fixed-opex").value), 0),
    ancillary: Math.max(Number($("#ancillary").value) / 100, 0)
  };
}

function calculateForecast(event) {
  if (event) event.preventDefault();
  if (!DATA) return;
  const inputs = readForecastInputs();
  const scenarios = [
    { name: "Low", multiplier: .8, color: COLORS.grey },
    { name: "Base", multiplier: 1, color: COLORS.teal },
    { name: "High", multiplier: 1.2, color: COLORS.blue }
  ].map(scenario => ({ ...scenario, result: forecastScenario(scenario.multiplier, inputs) }));
  const base = scenarios[1].result;
  const duration = inputs.useful / inputs.pT;
  const rte = inputs.effT * inputs.effP;
  $("#forecast-kpis").innerHTML = [
    kpiCard("Margen neto base", `${formatCompact(base.net)} €`, `${formatNumber(base.net / inputs.pT, 0)} EUR/MW-año`, COLORS.teal, "€"),
    kpiCard("Generación anual", `${formatCompact(base.annualGeneration)} MWh`, `${formatNumber(inputs.cycles * inputs.availability, 0)} ciclos disponibles`, COLORS.blue, "↗"),
    kpiCard("Compra / venta", `${formatNumber(base.buy, 1)} / ${formatNumber(base.sell, 1)}`, "€/MWh capturados", COLORS.orange, "⇄"),
    kpiCard("Duración útil", `${formatNumber(duration, 1)} h`, `${formatNumber(inputs.useful, 0)} MWh eléctricos`, COLORS.purple, "◷")
  ].join("");
  plot("forecast-chart", [{ type: "bar", x: scenarios.map(item => item.name), y: scenarios.map(item => item.result.net), marker: { color: scenarios.map(item => item.color) }, customdata: scenarios.map(item => item.result.net / inputs.pT), hovertemplate: "<b>%{x}</b><br>%{y:,.0f} €/año<br>%{customdata:,.0f} EUR/MW-año<extra></extra>" }], { showlegend: false, yaxis: { title: "EUR/año", tickformat: ",.2s" }, shapes: [{ type: "line", x0: -.5, x1: 2.5, y0: 0, y1: 0, line: { color: "#9aa7b4", width: 1 } }] });
  $("#forecast-assumptions").innerHTML = `<ul>
    <li><span>Capacidad útil</span><strong>${formatNumber(inputs.useful, 0)} MWh</strong></li>
    <li><span>Rendimiento ciclo</span><strong>${formatNumber(rte * 100, 1)} %</strong></li>
    <li><span>Compra base</span><strong>${formatNumber(base.buy, 2)} €/MWh</strong></li>
    <li><span>Venta base</span><strong>${formatNumber(base.sell, 2)} €/MWh</strong></li>
    <li><span>Margen por ciclo</span><strong>${formatNumber(base.cycleMargin, 0)} €</strong></li>
    <li><span>Días de precio usados</span><strong>${formatNumber(base.availableDays, 0)}</strong></li>
    <li><span>OPEX variable anual</span><strong>${formatNumber(base.variableOpex, 0)} €</strong></li>
    <li><span>OPEX fijo anual</span><strong>${formatNumber(base.fixedOpex, 0)} €</strong></li>
  </ul>`;
}

function renderAll() {
  renderSummary(); renderPlants(); renderEnergy(); renderMarkets(); renderQuality(); calculateForecast();
}

function updateFilters() {
  const start = $("#start-filter").value;
  const end = $("#end-filter").value;
  state.start = start <= end ? start : end;
  state.end = end >= start ? end : start;
  $("#start-filter").value = state.start; $("#end-filter").value = state.end;
  state.asset = $("#asset-filter").value; state.metric = $("#metric-filter").value;
  renderAll();
}

function initFilters() {
  const months = [...new Set(DATA.monthly.map(row => row.month))].sort();
  state.start = months[0]; state.end = months.at(-1);
  DATA.assets.forEach(asset => $("#asset-filter").insertAdjacentHTML("beforeend", `<option value="${escapeHtml(asset.asset)}">${escapeHtml(asset.asset)}</option>`));
  ["start-filter", "end-filter"].forEach(id => {
    months.forEach(month => $(`#${id}`).insertAdjacentHTML("beforeend", `<option value="${month}">${escapeHtml(formatMonth(month))}</option>`));
  });
  $("#start-filter").value = state.start; $("#end-filter").value = state.end;
  ["asset-filter", "start-filter", "end-filter", "metric-filter"].forEach(id => $(`#${id}`).addEventListener("change", updateFilters));
  $("#reset-filters").addEventListener("click", () => {
    $("#asset-filter").value = "ALL"; $("#start-filter").value = months[0]; $("#end-filter").value = months.at(-1); $("#metric-filter").value = "EUR"; updateFilters();
  });
}

function initTabs() {
  $$(".tab").forEach(button => button.addEventListener("click", () => {
    $$(".tab").forEach(item => item.classList.toggle("is-active", item === button));
    $$(".tab-panel").forEach(panel => panel.classList.toggle("is-active", panel.id === button.dataset.tab));
    history.replaceState(null, "", `#${button.dataset.tab}`);
    setTimeout(() => window.dispatchEvent(new Event("resize")), 20);
  }));
  const target = location.hash.slice(1);
  const button = $(`.tab[data-tab="${target}"]`);
  if (button) button.click();
}

function downloadCsv() {
  const headers = ["central", "operador", "mw", "ingreso_eur", "generacion_p48_mwh", "bombeo_p48_mwh", "precio_capturado_eur_mwh", "observado_pct"];
  const lines = tableAssetRows(currentRows()).map(row => [row.asset, row.operator, row.mw, row.revenue, row.generation, row.pumping, Number.isFinite(row.captured) ? row.captured : "", row.observed].map(value => `"${String(value).replaceAll('"', '""')}"`).join(";"));
  const blob = new Blob(["\ufeff" + [headers.join(";"), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `ingresos-bombeos-${state.start}-${state.end}.csv`; link.click(); URL.revokeObjectURL(url);
}

async function init() {
  try {
    if (window.DEMO_DATA) {
      DATA = window.DEMO_DATA;
    } else {
      const response = await fetch("data/demo-data.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`No se pudo cargar el snapshot (${response.status})`);
    DATA = await response.json();
    }
    $("#hero-period").textContent = `${formatDate(DATA.metadata.period_start)} – ${formatDate(DATA.metadata.period_end)}`;
    const quality = DATA.metadata.quality || {};
    if ((quality.critical_failed_months || []).length) {
      $("#hero-quality").textContent = `SNAPSHOT · ${quality.critical_failed_months.length} MESES A REVISAR`;
    }
    initFilters(); initTabs();
    $("#storage-mode").addEventListener("change", toggleStorageMode);
    $("#forecast-form").addEventListener("submit", calculateForecast);
    $("#download-csv").addEventListener("click", downloadCsv);
    renderAll();
    $("#loading").classList.add("is-hidden");
  } catch (error) {
    $("#loading").classList.add("is-hidden");
    $("#error-message").hidden = false;
    $("#error-message").textContent = `${error.message}. No se ha podido cargar el snapshot precargado.`;
    console.error(error);
  }
}

window.addEventListener("DOMContentLoaded", init);
