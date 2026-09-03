/* Dependency-free browser layer. CFG, AGG_MOTO and AGG_CAR are emitted by src/tco.py. */
(function () {
  "use strict";
  const root = typeof window !== "undefined" ? window : globalThis;
  const state = root.state = root.state || {
    vehicle: "car", grp: "naked", model: null, fuel: "petrol",
    age: 5, sell: 8, km: 8000, price: null, insurance: null,
    pump: null, service: null, inspection: null, market: null, registration: null,
    route: "dealer", pcc: false, categoryFilter: "any", make: null
  };
  const carAgg = typeof AGG_CAR === "undefined" ? null : AGG_CAR;
  const $ = id => typeof document === "undefined" ? null : document.getElementById(id);
  const fmt = (n, digits) => Number(n || 0).toLocaleString("pl-PL", {
    maximumFractionDigits: digits || 0, minimumFractionDigits: digits || 0
  });
  const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  })[char]);
  const lang = () => (typeof document === "undefined" ? "en" : document.documentElement.lang || "en");
  const text = key => (T[lang()] && T[lang()][key]) || T.en[key] || key;
  const template = (key, values) => Object.entries(values).reduce(
    (value, [name, replacement]) => value.replaceAll(`{${name}}`, String(replacement)), text(key)
  );
  const displayName = value => String(value || "").replace(/(^|[-\s])\S/g, c => c.toUpperCase()).replace(/\bBmw\b/g, "BMW");
  const normalizedName = value => String(value || "").normalize("NFKD").toLowerCase().replace(/[^a-z0-9]/g, "");

  function buildMotoCatalog(models) {
    const groups = new Map();
    Object.entries(models || {}).forEach(([key, model]) => {
      const normalized = normalizedName(key);
      if (!groups.has(normalized)) groups.set(normalized, []);
      groups.get(normalized).push({ key, model });
    });
    return [...groups.values()].map(group => {
      group.sort((a, b) => Number(b.model.n_samples || 0) - Number(a.model.n_samples || 0) || a.key.localeCompare(b.key));
      const primary = group[0];
      return {
        key: primary.key,
        label: displayName(primary.key),
        category: primary.model.category || "mixed",
        status: primary.model.category_status || "clear",
        confidence: primary.model.category_confidence || null,
        samples: Number(primary.model.n_samples || 0),
        reliable: primary.model.reliable !== false,
        points: primary.model.points || [],
        aliases: group.map(item => item.key),
        search: group.map(item => normalizedName(item.key)).join(" ")
      };
    }).filter(profile => profile.reliable).sort((a, b) => a.label.localeCompare(b.label));
  }

  const motoProfiles = typeof AGG_MOTO === "undefined" ? [] : buildMotoCatalog(AGG_MOTO.models);
  const carProfiles = !carAgg || !carAgg.models ? [] : Object.keys(carAgg.models).map(key => {
    const [make, ...modelParts] = key.split(/\s+/);
    return {
      key, make, label: displayName(key), modelLabel: displayName(modelParts.join(" ") || key),
      category: null, status: "clear", samples: Number(carAgg.models[key].n_samples || 0),
      reliable: carAgg.models[key].reliable !== false, points: carAgg.models[key].points || [],
      aliases: [key], search: normalizedName(key)
    };
  }).sort((a, b) => a.make.localeCompare(b.make) || a.modelLabel.localeCompare(b.modelLabel));
  const carMakes = [...new Set(carProfiles.map(profile => profile.make))];
  root.buildMotoCatalog = buildMotoCatalog;
  function yearWord(value) {
    const n = Math.abs(Number(value));
    if (lang() === "en") return n === 1 ? "year" : "years";
    if (n % 10 === 1 && n % 100 !== 11) return "rok";
    if ([2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100)) return "lata";
    return "lat";
  }

  function profiles() { return state.vehicle === "moto" ? motoProfiles : carProfiles; }
  function selectedProfile() { return profiles().find(profile => profile.key === state.model) || null; }

  function curveQuality(points, reliable) {
    const ages = (points || []).map(point => Number(point.age)).filter(Number.isFinite).sort((a, b) => a - b);
    const maxGap = ages.slice(1).reduce((gap, age, index) => Math.max(gap, age - ages[index]), 0);
    return {
      minAge: ages.length ? ages[0] : null, maxAge: ages.length ? ages[ages.length - 1] : null,
      points: ages.length, maxGap, limited: reliable === false || maxGap > 1,
      extreme: ages.length < 6 || maxGap >= 8
    };
  }

  function curveContext() {
    const profile = selectedProfile();
    const data = state.vehicle === "car" ? carAgg : AGG_MOTO;
    const model = profile && data && data.models ? data.models[profile.key] : null;
    const modelPoints = model && model.points ? model.points : [];
    const quality = curveQuality(modelPoints, model ? model.reliable : true);
    if (state.vehicle === "moto" && quality.extreme && model && model.category) {
      const category = AGG_MOTO.categories && AGG_MOTO.categories[model.category];
      if (category && category.points && category.points.length) {
        return { points: category.points, modelPoints, quality, fallback: true, category: model.category };
      }
    }
    if (modelPoints.length) return { points: modelPoints, modelPoints, quality, fallback: false, category: model && model.category };
    if (state.vehicle === "moto" && AGG_MOTO.categories && AGG_MOTO.categories[state.grp]) {
      return { points: AGG_MOTO.categories[state.grp].points || [], modelPoints: [], quality, fallback: true, category: state.grp };
    }
    const first = data && data.models && Object.keys(data.models)[0];
    return { points: first ? (data.models[first].points || []) : [], modelPoints: [], quality, fallback: false, category: null };
  }
  root.curveQuality = curveQuality;
  root.curveContext = curveContext;

  function constrainTimeline(changed) {
    const context = curveContext();
    const points = context.fallback && context.modelPoints.length ? context.modelPoints : context.points;
    if (!points.length) return;
    const ages = points.map(point => Number(point.age)).filter(Number.isFinite);
    const dataMin = Math.min(...ages), dataMax = Math.max(...ages);
    // A vehicle can be purchased new (age 0); sale still requires one year.
    const ageMin = Math.max(0, Math.ceil(dataMin));
    const maxAge = Math.max(ageMin + 1, Math.floor(dataMax));
    const integer = (value, fallback) => {
      const number = Number(value);
      return Number.isFinite(number) ? Math.round(number) : fallback;
    };
    const requestedAge = integer(state.age, ageMin);
    const requestedSell = integer(state.sell, ageMin + 1);
    if (changed === "age") {
      // Moving purchase age preserves the sale age whenever possible.
      state.sell = Math.min(maxAge, Math.max(ageMin + 1, requestedSell));
      state.age = Math.min(state.sell - 1, Math.max(ageMin, requestedAge));
    } else if (changed === "sell") {
      // Moving sale age preserves the purchase age whenever possible.
      state.age = Math.min(maxAge - 1, Math.max(ageMin, requestedAge));
      state.sell = Math.min(maxAge, Math.max(state.age + 1, requestedSell));
    } else {
      state.age = Math.min(maxAge - 1, Math.max(ageMin, requestedAge));
      state.sell = Math.min(maxAge, Math.max(state.age + 1, requestedSell));
    }
    // Keep both visual tracks on the same 0..maxAge scale. Their legal
    // relationship is enforced in state, while number inputs expose the
    // tighter endpoint-specific bounds.
    const bounds = [["age", ageMin, state.sell - 1], ["sell", state.age + 1, maxAge]];
    bounds.forEach(([id, min, max]) => {
      const range = $(id), number = $(`${id}Number`);
      if (range) { range.min = String(ageMin); range.max = String(maxAge); }
      if (number) { number.min = String(min); number.max = String(max); }
    });
  }
  root.constrainTimeline = constrainTimeline;

  function curve() {
    return curveContext().points;
  }

  function interp(points, age) {
    if (!points.length) return null;
    const p = points.slice().sort((a, b) => a.age - b.age);
    if (age <= p[0].age) return Number(p[0].smooth);
    if (age >= p[p.length - 1].age) return Number(p[p.length - 1].smooth);
    for (let i = 1; i < p.length; i += 1) if (age <= p[i].age) {
      const t = (age - p[i - 1].age) / ((p[i].age - p[i - 1].age) || 1);
      return Number(p[i - 1].smooth) + t * (Number(p[i].smooth) - Number(p[i - 1].smooth));
    }
    return Number(p[p.length - 1].smooth);
  }

  function fuelDefault() {
    const key = state.vehicle === "moto" ? "petrol95" : ((CFG.carFuel[state.fuel] || CFG.carFuel.petrol).fuel);
    const value = Number((CFG.fuel.prices || {})[key]);
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  function defaults() {
    if (state.vehicle === "moto") {
      const selected = AGG_MOTO.models && state.model ? AGG_MOTO.models[state.model] : null;
      const category = selected && selected.category ? selected.category : state.grp;
      const d = CFG.categories[category] || CFG.categories.naked;
      return { per100: d.fuel_per100, service: d.service_per1000, insurance: d.insurance_yr, inspection: CFG.inspectionMoto };
    }
    const d = CFG.carFuel[state.fuel] || CFG.carFuel.petrol;
    return { per100: d.per100, service: CFG.carService, insurance: CFG.carInsurance, inspection: CFG.inspectionCar };
  }

  function compute() {
    const d = defaults(), context = curveContext(), points = context.points;
    const hold = Number(state.sell) - Number(state.age);
    const now = interp(points, Number(state.age)), later = interp(points, Number(state.sell));
    if (now === null || later === null || !(hold > 0)) return { total: null, items: [], shares: {} };
    let modelNow = now;
    if (context.fallback && context.modelPoints.length) {
      const reference = context.modelPoints.reduce((nearest, point) => (
        Math.abs(Number(point.age) - Number(state.age)) < Math.abs(Number(nearest.age) - Number(state.age)) ? point : nearest
      ));
      const categoryReference = interp(points, Number(reference.age));
      modelNow = categoryReference ? now * Number(reference.smooth) / categoryReference : Number(reference.smooth);
    }
    const paid = state.price !== null && Number(state.price) >= 0 ? Number(state.price) : (modelNow ?? now);
    const scale = now ? paid / now : 1;
    const depreciation = Math.max(0, paid - later * scale) / hold;
    const pump = state.pump !== null && Number(state.pump) > 0 ? Number(state.pump) : fuelDefault();
    if (!(pump > 0)) return { total: null, items: [], shares: {} };
    const fuel = d.per100 / 100 * Number(state.km) * pump;
    const serviceRate = state.service !== null ? Number(state.service) : d.service;
    const service = serviceRate * Number(state.km) / 1000 * (1 + CFG.serviceAgeK * (Number(state.age) + Number(state.sell)) / 2);
    const insurance = state.insurance !== null ? Number(state.insurance) : d.insurance;
    const inspection = Number(state.inspection ?? d.inspection ?? 0);
    const basis = state.market !== null && Number(state.market) > 0 ? Number(state.market) : paid;
    const pcc = state.route === "private" && state.pcc ? basis * CFG.pccRate / hold : 0;
    const registration = state.registration !== null && state.registration !== undefined ? Number(state.registration) : CFG.registration;
    const fees = registration / hold + pcc;
    const raw = { depreciation, fuel, service, insurance, inspection, fees };
    const total = Math.round(Object.values(raw).reduce((sum, value) => sum + value, 0));
    const shares = {};
    Object.keys(raw).forEach(key => { shares[key] = total ? Math.round(raw[key] / total * 10000) / 100 : 0; });
    if (total) shares.fees = Math.round((shares.fees + 100 - Object.values(shares).reduce((a, b) => a + b, 0)) * 100) / 100;
    const items = CFG.components.map(([key, label]) => ({ key, label, pln: Math.round(raw[key]) }));
    return {
      total, items, shares, paid: Math.round(paid), end: Math.round(later * scale),
      lifetime: Math.round(total * hold), perKm: Number((total / Number(state.km)).toFixed(2)),
      deprShare: Math.round(shares.depreciation || 0), endAge: Number(state.sell), scale
    };
  }
  root.compute = compute;

  function profileName() {
    const selected = selectedProfile();
    return selected ? selected.label : displayName(state.vehicle === "car" ? "car" : "motorcycle");
  }

  let pickerMatches = [];
  let pickerIndex = -1;

  function categoryLabel(category) {
    const labels = CFG.categoryLabels[lang()] || CFG.categoryLabels.en;
    return labels[category] || category;
  }

  function profileMatches(profile, query) {
    return !query || profile.search.includes(query) || normalizedName(profile.label).includes(query);
  }

  function filteredProfiles(query) {
    return profiles().filter(profile => profileMatches(profile, query) && (
      (state.vehicle !== "moto" || state.categoryFilter === "any" || profile.category === state.categoryFilter) &&
      (state.vehicle !== "car" || profile.make === state.make)
    ));
  }

  function profileInputLabel(profile) {
    return state.vehicle === "car" ? profile.modelLabel : profile.label;
  }

  function closePicker() {
    const input = $("profileSearch"), results = $("profileResults");
    if (!input || !results) return;
    results.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant");
    pickerIndex = -1;
  }

  function renderPickerResults(open) {
    const input = $("profileSearch"), results = $("profileResults");
    if (!input || !results) return;
    const query = normalizedName(input.value);
    pickerMatches = filteredProfiles(query);
    const shown = pickerMatches.slice(0, 80);
    if (!shown.length) {
      results.innerHTML = `<div class="profile-empty">${escapeHtml(text("no_matches"))}</div>`;
    } else {
      results.innerHTML = shown.map((profile, index) => {
        const detail = state.vehicle === "moto" ? categoryLabel(profile.category) : displayName(profile.make);
        const warning = profile.status === "variant_required" ? `, ${text("variant_required")}` : "";
        return `<div class="profile-option" id="profileOption${index}" role="option" aria-selected="false" data-model="${escapeHtml(profile.key)}"><span>${escapeHtml(profileInputLabel(profile))}</span><small>${escapeHtml(detail + warning)}</small></div>`;
      }).join("") + (pickerMatches.length > shown.length
        ? `<div class="profile-more">${escapeHtml(template("more_matches", { shown: shown.length, total: pickerMatches.length }))}</div>` : "");
    }
    if (open) { results.hidden = false; input.setAttribute("aria-expanded", "true"); }
    pickerIndex = -1;
  }

  function renderModelMeta() {
    const mount = $("modelMeta"), profile = selectedProfile();
    if (!mount || !profile) return;
    const context = curveContext(), quality = context.quality;
    const parts = state.vehicle === "moto" ? [`<strong>${escapeHtml(categoryLabel(profile.category))}</strong>`] : [];
    parts.push(escapeHtml(template("curve_coverage", {
      min: quality.minAge ?? "—", max: quality.maxAge ?? "—", points: quality.points, samples: fmt(profile.samples)
    })));
    let note = parts.join(", ");
    if (profile.aliases.length > 1) note += `<span class="model-warning">${escapeHtml(text("alias_notice"))}</span>`;
    if (profile.status === "variant_required") note += `<span class="model-warning"><strong>${escapeHtml(text("variant_required"))}.</strong> ${escapeHtml(text("variant_warning"))}</span>`;
    if (context.fallback) {
      note += `<span class="model-note"><span class="model-note-label">${escapeHtml(text("curve_basis"))}:</span> ${escapeHtml(template("curve_category", { category: categoryLabel(context.category) }))}</span>`;
    } else if (quality.points < 6) {
      note += `<span class="model-note"><span class="model-note-label">${escapeHtml(text("curve_basis"))}:</span> ${escapeHtml(text("curve_sparse"))}</span>`;
    } else if (quality.maxGap > 1) {
      note += `<span class="model-note"><span class="model-note-label">${escapeHtml(text("curve_basis"))}:</span> ${escapeHtml(text("curve_interpolated"))}</span>`;
    } else if (!profile.reliable) {
      note += `<span class="model-note"><span class="model-note-label">${escapeHtml(text("curve_basis"))}:</span> ${escapeHtml(text("curve_uncertain"))}</span>`;
    }
    mount.innerHTML = note;
  }

  function chooseProfile(key) {
    const profile = profiles().find(item => item.key === key);
    if (!profile) return;
    state.model = profile.key;
    if (state.vehicle === "moto") state.grp = profile.category;
    state.price = null; state.service = null;
    $("profileSearch").value = profileInputLabel(profile);
    closePicker(); constrainTimeline(); renderModelMeta(); render();
  }

  function renderCategoryFilter() {
    const panel = $("modelFilters"), select = $("categoryFilter");
    if (!panel || !select) return;
    panel.hidden = state.vehicle !== "moto";
    if (panel.hidden) return;
    const counts = new Map();
    motoProfiles.forEach(profile => counts.set(profile.category, (counts.get(profile.category) || 0) + 1));
    select.innerHTML = `<option value="any">${escapeHtml(text("any_category"))}</option>` + CFG.categoryOrder
      .filter(category => counts.has(category))
      .map(category => `<option value="${escapeHtml(category)}">${escapeHtml(categoryLabel(category))} (${counts.get(category)})</option>`).join("");
    if (!counts.has(state.categoryFilter)) state.categoryFilter = "any";
    select.value = state.categoryFilter;
  }

  function renderCarMakeFilter() {
    const field = $("carMakeField"), select = $("carMake");
    if (!field || !select) return;
    field.hidden = state.vehicle !== "car";
    if (field.hidden || !carMakes.length) return;
    const selected = carProfiles.find(profile => profile.key === state.model);
    if (!state.make || !carMakes.includes(state.make)) {
      state.make = selected ? selected.make : (carMakes.includes("volkswagen") ? "volkswagen" : carMakes[0]);
    }
    select.innerHTML = carMakes.map(make => `<option value="${escapeHtml(make)}">${escapeHtml(displayName(make))}</option>`).join("");
    select.value = state.make;
  }

  function renderProfiles() {
    renderCarMakeFilter();
    const available = profiles().filter(profile => state.vehicle !== "car" || profile.make === state.make);
    const input = $("profileSearch");
    if (!input || !available.length) return;
    let selected = available.find(profile => profile.key === state.model);
    if (!selected && state.model) selected = available.find(profile => profile.aliases.includes(state.model));
    if (!selected) {
      const preferred = state.vehicle === "car" ? "volkswagen golf" : "Honda CB";
      selected = available.find(profile => profile.key === preferred) || available[0];
    }
    state.model = selected.key;
    if (state.vehicle === "moto") state.grp = selected.category;
    input.value = profileInputLabel(selected);
    input.placeholder = text("model_search");
    renderCategoryFilter(); renderModelMeta(); constrainTimeline();
  }

  function renderFuelTypes() {
    const select = $("fuelType"), field = $("fuelTypeField");
    if (!select || !field) return;
    field.hidden = state.vehicle !== "car";
    const labels = CFG.carFuelLabels[lang()] || CFG.carFuelLabels.en;
    select.innerHTML = Object.keys(CFG.carFuel).map(key => `<option value="${key}">${escapeHtml(labels[key])}</option>`).join("");
    select.value = state.fuel;
  }

  function componentLabel(key) {
    return text({ fuel: "fuel_cost", service: "service_label", insurance: "insurance_cost", inspection: "inspection_label", fees: "fees" }[key] || key);
  }

  function summary(c) {
    const name = escapeHtml(profileName());
    const hold = Number(state.sell) - Number(state.age);
    if (lang() === "pl") return `<strong>${escapeHtml(String(state.age))}-letni ${name}</strong>, użytkowany przez <strong>${escapeHtml(String(hold))} ${yearWord(hold)}</strong> i przejeżdżający <strong>${fmt(state.km)} km rocznie</strong>. Utrata wartości stanowi około <strong>${c.deprShare}%</strong> szacunku.`;
    return `A <strong>${escapeHtml(String(state.age))}-year-old ${name}</strong>, kept for <strong>${escapeHtml(String(hold))} ${yearWord(hold)}</strong> and driven <strong>${fmt(state.km)} km a year</strong>. Depreciation accounts for about <strong>${c.deprShare}%</strong> of the estimate.`;
  }

  let chartGeom = null, chartKeyAge = null, chartPinned = false;

  function chartValueAt(points, age) {
    if (age <= points[0].age) return Number(points[0].smooth);
    if (age >= points[points.length - 1].age) return Number(points[points.length - 1].smooth);
    for (let i = 1; i < points.length; i++) {
      if (age <= points[i].age) {
        const a = points[i - 1], b = points[i];
        const t = (age - Number(a.age)) / ((Number(b.age) - Number(a.age)) || 1);
        return Number(a.smooth) + t * (Number(b.smooth) - Number(a.smooth));
      }
    }
    return Number(points[points.length - 1].smooth);
  }

  function chartAgeAt(mount, clientX) {
    const g = chartGeom, svg = mount.querySelector("svg");
    if (!g || !svg) return null;
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return null;
    const xView = (clientX - rect.left) / rect.width * g.w;
    const t = (xView - g.px) / ((g.w - g.px * 2) || 1);
    return g.minX + Math.min(1, Math.max(0, t)) * (g.maxX - g.minX);
  }

  function chartCrossesGap(points, age) {
    for (let index = 1; index < points.length; index++) {
      const before = Number(points[index - 1].age), after = Number(points[index].age);
      if (age > before && age < after) return after - before > 1;
    }
    return false;
  }

  function chartYearTicks(minAge, maxAge, availableWidth) {
    const min = Number(minAge), max = Number(maxAge), span = max - min;
    if (!(span > 0)) return [min];
    const intervals = Math.max(2, Math.min(6, Math.floor((Number(availableWidth) || 760) / 65)));
    const targetStep = span / intervals;
    const step = [1, 2, 3, 5, 10, 20, 50].find(value => value >= targetStep) || Math.ceil(targetStep / 50) * 50;
    const ticks = [min];
    for (let age = Math.ceil(min / step) * step; age < max; age += step) {
      if (age - min >= step * .6 && max - age >= step * .6) ticks.push(age);
    }
    ticks.push(max);
    return [...new Set(ticks)];
  }

  function chartInspect(mount, age) {
    const g = chartGeom;
    if (!mount || !g || age === null || age === undefined) return;
    age = Math.min(g.maxX, Math.max(g.minX, Number(age)));
    chartKeyAge = age;
    const hover = mount.querySelector(".chart-hover"), tip = mount.querySelector(".chart-tip");
    if (!hover || !tip) return;
    const value = chartValueAt(g.points, age), x = g.sx(age), y = g.sy(value);
    hover.hidden = false;
    const line = hover.querySelector(".chart-guide"), dot = hover.querySelector(".chart-dot");
    line.setAttribute("x1", x.toFixed(1)); line.setAttribute("x2", x.toFixed(1));
    dot.setAttribute("cx", x.toFixed(1)); dot.setAttribute("cy", y.toFixed(1));
    tip.hidden = false;
    const gapNote = chartCrossesGap(g.points, age) ? ` — ${text("interpolated_value")}` : "";
    tip.textContent = `${Math.round(age)} ${yearWord(Math.round(age))} — ${fmt(value)} zł${gapNote}`;
    mount.setAttribute("aria-valuenow", age.toFixed(2));
    mount.setAttribute("aria-valuetext", tip.textContent);
    const edge = x / g.w;
    tip.classList.toggle("edge-left", edge < 0.12);
    tip.classList.toggle("edge-right", edge > 0.88);
    tip.style.left = `${(edge * 100).toFixed(1)}%`;
    const svg = mount.querySelector("svg");
    const renderedHeight = svg ? svg.getBoundingClientRect().height : g.h;
    tip.style.top = `${(y / g.h * renderedHeight).toFixed(1)}px`;
  }

  function chartHide(mount) {
    if (!mount) return;
    chartKeyAge = null;
    const hover = mount.querySelector(".chart-hover"), tip = mount.querySelector(".chart-tip");
    if (hover) hover.hidden = true;
    if (tip) tip.hidden = true;
  }

  function drawChart(c) {
    const mount = $("chart"), context = curveContext();
    // Never present a broad category fallback as if it were this model's
    // depreciation history. Sparse model points are more honest than invented
    // intermediate drops; the calculation may still use the category basis.
    const rawPoints = context.modelPoints.length ? context.modelPoints : context.points;
    if (!mount || !rawPoints.length) {
      chartGeom = null;
      if (mount) mount.textContent = text("no_curve");
      ["chartStart", "chartLoss", "chartEnd"].forEach(id => { if ($(id)) $(id).textContent = "—"; });
      return;
    }
    const scale = Number.isFinite(Number(c.scale)) ? Number(c.scale) : 1;
    const sparseModel = context.modelPoints.length && context.quality.points < 6;
    const points = rawPoints.map(point => ({
      ...point,
      // Sparse models show their observed medians, never an artificial flat
      // smoothing anchor.
      smooth: Number(sparseModel && Number.isFinite(Number(point.median)) ? point.median : point.smooth) * scale
    }));
    const w = 760, h = 180, px = 18, py = 18;
    const minX = points[0].age, maxX = points[points.length - 1].age;
    const vals = points.map(p => Number(p.smooth)), minY = Math.min(...vals), maxY = Math.max(...vals);
    const ySpan = maxY - minY;
    const sx = x => px + (x - minX) / ((maxX - minX) || 1) * (w - px * 2);
    const sy = y => ySpan ? h - py - (y - minY) / ySpan * (h - py * 2) : h / 2;
    const segments = points.slice(1).map((point, index) => {
      const before = points[index], interpolated = Number(point.age) - Number(before.age) > 1;
      return `<line class="chart-line${interpolated ? " interpolated" : ""}" x1="${sx(before.age).toFixed(1)}" y1="${sy(before.smooth).toFixed(1)}" x2="${sx(point.age).toFixed(1)}" y2="${sy(point.smooth).toFixed(1)}"/>`;
    }).join("");
    const hasGap = points.some((point, index) => index > 0 && Number(point.age) - Number(points[index - 1].age) > 1);
    document.querySelectorAll(".key-gap").forEach(key => { key.hidden = !hasGap; });
    const observations = points.map(point => `<circle class="chart-observation" cx="${sx(point.age).toFixed(1)}" cy="${sy(point.smooth).toFixed(1)}" r="2.5"/>`).join("");
    const yearTicks = chartYearTicks(minX, maxX, mount.clientWidth);
    const yearLines = yearTicks.map(age => `<line class="chart-year-line" x1="${sx(age).toFixed(1)}" x2="${sx(age).toFixed(1)}" y1="${py}" y2="${h - py}"/>`).join("");
    const yearLabels = yearTicks.map((age, index) => {
      const edge = index === 0 ? " first" : index === yearTicks.length - 1 ? " last" : "";
      return `<span class="chart-year${edge}" style="left:${(sx(age) / w * 100).toFixed(2)}%">${escapeHtml(String(age))} ${escapeHtml(yearWord(age))}</span>`;
    }).join("");
    const a = Math.max(minX, Number(state.age)), b = Math.min(maxX, Number(state.sell));
    mount.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${escapeHtml(text("chart"))}">${yearLines}<rect x="${sx(a)}" y="${py}" width="${Math.max(0, sx(b) - sx(a))}" height="${h - py * 2}" fill="var(--accent)" opacity=".08"/>${segments}${observations}<line x1="${sx(a)}" x2="${sx(a)}" y1="${py}" y2="${h - py}" stroke="var(--accent)"/><line x1="${sx(b)}" x2="${sx(b)}" y1="${py}" y2="${h - py}" stroke="var(--accent)"/><g class="chart-hover" hidden><line class="chart-guide" y1="${py}" y2="${h - py}"/><circle class="chart-dot" r="4"/></g></svg><div class="chart-years" aria-hidden="true">${yearLabels}</div><div class="chart-tip" hidden></div>`;
    mount.setAttribute("role", "slider");
    mount.setAttribute("aria-label", text("chart"));
    mount.setAttribute("aria-orientation", "horizontal");
    mount.setAttribute("aria-valuemin", String(minX));
    mount.setAttribute("aria-valuemax", String(maxX));
    mount.setAttribute("aria-keyshortcuts", "ArrowLeft ArrowRight Home End");
    chartGeom = { points, minX, maxX, sx, sy, px, py, w, h };
    const inspectedAge = chartKeyAge === null ? Math.min(maxX, Math.max(minX, Number(state.age))) : chartKeyAge;
    const inspectedValue = chartValueAt(points, inspectedAge);
    mount.setAttribute("aria-valuenow", inspectedAge.toFixed(2));
    mount.setAttribute("aria-valuetext", `${Math.round(inspectedAge)} ${yearWord(Math.round(inspectedAge))} — ${fmt(inspectedValue)} zł`);
    if (chartKeyAge !== null) chartInspect(mount, chartKeyAge);
    $("chartStart").textContent = `${text("buy_value")}: ${fmt(c.paid)} zł ${text("at_age")} ${state.age} ${yearWord(state.age)}`;
    $("chartLoss").textContent = `−${fmt(Math.max(0, c.paid - c.end))} zł`;
    const endAge = c.endAge;
    $("chartEnd").textContent = `${text("sell_value")}: ${fmt(c.end)} zł ${text("at_age")} ${endAge} ${yearWord(endAge)}`;
  }

  function render() {
    constrainTimeline();
    const d = defaults(), c = compute();
    [["ageNumber", state.age], ["sellNumber", state.sell], ["kmNumber", state.km]].forEach(([id, value]) => {
      const el = $(id); if (el && !el.matches(":focus")) el.value = value;
    });
    [["age", state.age], ["sell", state.sell], ["km", state.km]].forEach(([id, value]) => {
      const el = $(id); if (el && !el.matches(":focus") && Number(el.value) !== Number(value)) el.value = value;
    });
    if ($("ageUnit")) $("ageUnit").textContent = lang() === "en" ? `${yearWord(state.age)} old` : yearWord(state.age);
    if ($("sellUnit")) $("sellUnit").textContent = lang() === "en" ? `${yearWord(state.sell)} old` : yearWord(state.sell);
    if ($("pump") && !$("pump").matches(":focus")) $("pump").value = Number(state.pump || fuelDefault()).toFixed(2);
    if ($("svc") && !$("svc").matches(":focus")) $("svc").value = state.service ?? d.service;
    if ($("ins") && !$("ins").matches(":focus")) $("ins").value = state.insurance ?? "";
    if ($("inspection") && !$("inspection").matches(":focus")) $("inspection").value = state.inspection ?? d.inspection;
    if ($("registration") && !$("registration").matches(":focus")) $("registration").value = state.registration ?? CFG.registration;
    if ($("market")) $("market").disabled = state.route !== "private";
    if ($("pcc")) { $("pcc").disabled = state.route !== "private"; $("pcc").checked = state.route === "private" && state.pcc; }
    document.querySelectorAll("[data-route]").forEach(el => el.setAttribute("aria-pressed", String(el.dataset.route === state.route)));
    document.querySelectorAll("[data-veh]").forEach(el => el.setAttribute("aria-pressed", String(el.dataset.veh === state.vehicle)));
    const f = CFG.fuel;
    const age = Math.floor((Date.now() - new Date(`${f.observed_at}T00:00:00Z`).getTime()) / 86400000);
    if ($("fuelnote")) $("fuelnote").textContent = `${text("source")}: ${f.source} (${f.observed_at}). ${age > 14 || f.stale ? text("stale") : text("fresh")}`;
    if (c.total === null) {
      $("annual").textContent = "—"; $("summary").textContent = text("no_curve"); $("rows").innerHTML = ""; drawChart(c); return;
    }
    $("annual").textContent = fmt(c.total);
    $("summary").innerHTML = summary(c);
    $("rows").innerHTML = c.items.map(item => `<div class="cost-row" tabindex="0"><span class="row-name">${escapeHtml(componentLabel(item.key))}</span><span class="bar"><i style="--width:${c.shares[item.key]}%"></i></span><span class="row-value">${fmt(item.pln)}<small class="row-share">${c.shares[item.key]}%</small></span></div>`).join("") + `<div class="cost-row total" tabindex="0"><span class="row-name">${escapeHtml(text("total"))}</span><span class="bar"><i style="--width:100%"></i></span><span class="row-value">${fmt(c.total)}<small class="row-share">100%</small></span></div>`;
    drawChart(c);
  }

  function translate(next) {
    document.documentElement.lang = next;
    document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = text(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-aria-label]").forEach(el => el.setAttribute("aria-label", text(el.dataset.i18nAriaLabel)));
    document.querySelectorAll("[data-i18n-placeholder]").forEach(el => el.setAttribute("placeholder", text(el.dataset.i18nPlaceholder)));
    document.querySelectorAll("[data-lang]").forEach(el => el.setAttribute("aria-pressed", String(el.dataset.lang === next)));
    document.title = text("title");
    renderProfiles(); renderFuelTypes(); render();
  }

  function optionalNumber(value) { return value === "" ? null : Number(value); }
  function bind() {
    if (typeof document === "undefined") return;
    renderProfiles(); renderFuelTypes();
    ["age", "sell", "km"].forEach(id => {
      const range = $(id), number = $(id + "Number");
      range.addEventListener("input", () => {
        state[id] = Number(range.value);
        constrainTimeline(id === "age" || id === "sell" ? id : null);
        if (Number(range.value) !== Number(state[id])) range.value = state[id];
        render();
      });
      number.addEventListener("change", () => {
        const min = Number(number.min), max = Number(number.max);
        state[id] = Math.min(max, Math.max(min, Number(number.value) || min));
        constrainTimeline(id === "age" || id === "sell" ? id : null);
        range.value = state[id];
        render();
      });
    });
    [["price", "price"], ["ins", "insurance"], ["pump", "pump"], ["svc", "service"], ["market", "market"], ["registration", "registration"], ["inspection", "inspection"]].forEach(([id, key]) => {
      $(id).addEventListener("input", event => { state[key] = optionalNumber(event.target.value); render(); });
    });
    $("profileSearch").addEventListener("focus", event => {
      event.target.value = ""; renderPickerResults(true);
    });
    $("profileSearch").addEventListener("input", () => renderPickerResults(true));
    $("profileSearch").addEventListener("keydown", event => {
      const results = $("profileResults");
      if (event.key === "Escape") {
        const selected = selectedProfile(); if (selected) event.target.value = selected.label;
        closePicker(); return;
      }
      if (!["ArrowDown", "ArrowUp", "Enter"].includes(event.key)) return;
      if (results.hidden) renderPickerResults(true);
      const options = [...results.querySelectorAll("[role=option]")];
      if (!options.length) return;
      event.preventDefault();
      if (event.key === "Enter") {
        if (pickerIndex >= 0 && pickerMatches[pickerIndex]) chooseProfile(pickerMatches[pickerIndex].key);
        return;
      }
      pickerIndex = event.key === "ArrowDown" ? Math.min(options.length - 1, pickerIndex + 1) : Math.max(0, pickerIndex - 1);
      options.forEach((option, index) => option.setAttribute("aria-selected", String(index === pickerIndex)));
      event.target.setAttribute("aria-activedescendant", options[pickerIndex].id);
      options[pickerIndex].scrollIntoView({ block: "nearest" });
    });
    $("profileSearch").addEventListener("blur", event => {
      setTimeout(() => {
        const selected = selectedProfile(); if (selected) event.target.value = profileInputLabel(selected);
        closePicker();
      }, 100);
    });
    $("profileResults").addEventListener("mousedown", event => {
      const option = event.target.closest("[data-model]");
      if (option) { event.preventDefault(); chooseProfile(option.dataset.model); }
    });
    $("categoryFilter").addEventListener("change", event => {
      state.categoryFilter = event.target.value; $("profileSearch").value = ""; renderPickerResults(true); $("profileSearch").focus();
    });
    $("carMake").addEventListener("change", event => {
      state.make = event.target.value; state.model = null; closePicker(); renderProfiles(); render();
    });
    $("resetModelFilter").addEventListener("click", () => {
      state.categoryFilter = "any"; renderCategoryFilter(); $("profileSearch").value = ""; renderPickerResults(true); $("profileSearch").focus();
    });
    $("fuelType").addEventListener("change", event => { state.fuel = event.target.value; state.pump = null; render(); });
    document.querySelectorAll("[data-route]").forEach(button => button.addEventListener("click", () => {
      state.route = button.dataset.route; state.pcc = state.route === "private"; render();
    }));
    $("pcc").addEventListener("change", () => { state.pcc = $("pcc").checked; render(); });
    document.querySelectorAll("[data-lang]").forEach(button => button.addEventListener("click", () => translate(button.dataset.lang)));
    document.querySelectorAll("[data-veh]").forEach(button => button.addEventListener("click", () => {
      state.vehicle = button.dataset.veh; state.model = null; state.insurance = null; state.pump = null;
      state.service = null; state.inspection = null; state.price = null; state.categoryFilter = "any";
      closePicker(); renderProfiles(); renderFuelTypes(); render();
    }));
    const chart = $("chart");
    if (chart) {
      chart.tabIndex = 0;
      chart.setAttribute("aria-label", text("chart"));
      chart.addEventListener("pointermove", event => chartInspect(chart, chartAgeAt(chart, event.clientX)));
      chart.addEventListener("pointerdown", event => {
        chartInspect(chart, chartAgeAt(chart, event.clientX));
        if (event.pointerType !== "mouse") {
          chartPinned = true;
          chart.focus({ preventScroll: true });
        }
      });
      chart.addEventListener("pointerleave", () => { if (!chartPinned) chartHide(chart); });
      chart.addEventListener("focus", () => {
        if (chartKeyAge === null && chartGeom) chartInspect(chart, Number(state.age));
      });
      chart.addEventListener("blur", () => { chartPinned = false; chartHide(chart); });
      chart.addEventListener("keydown", event => {
        if (!chartGeom) return;
        const step = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0;
        if (!step && event.key !== "Home" && event.key !== "End") return;
        event.preventDefault();
        const base = chartKeyAge === null ? Math.min(chartGeom.maxX, Math.max(chartGeom.minX, Number(state.age))) : chartKeyAge;
        const next = event.key === "Home" ? chartGeom.minX : event.key === "End" ? chartGeom.maxX
          : Math.min(chartGeom.maxX, Math.max(chartGeom.minX, base + step));
        chartInspect(chart, next);
      });
      document.addEventListener("pointerdown", event => {
        if (chartPinned && !chart.contains(event.target)) {
          chartPinned = false;
          chartHide(chart);
      }
    });
  }
    render();
  }
  if (typeof document !== "undefined") document.addEventListener("DOMContentLoaded", bind);
})();
