// Public static site + a tiny live fuel-price endpoint.
//
// The site is hosted as Workers Static Assets. With assets.run_worker_first =
// false (see wrangler.jsonc) every real file is served straight from the edge
// WITHOUT invoking this Worker — the site is fully public. This Worker only runs
// for paths that don't match an asset, which is exactly one route:
//
//   GET /api/fuel  → current PL pump prices (zł/l, zł/kWh) as JSON.
//
// The calculators fetch it on load to seed their fuel-price defaults; if it
// fails they keep the static fallback below, so the page is never blocked on it.

// Today's standard-rate ballparks — the answer when the upstream is unreachable.
const FALLBACK = { petrol: 6.49, diesel: 6.59, lpg: 2.8, electric: 1.1 };

// paliwo.today: free, no-key JSON. `?type=` is PB95 | PB98 | ON; without it the
// endpoint returns the latest price for every fuel type. LPG/electricity aren't
// covered there, so those keep the static fallback.
const SOURCE = "https://api.paliwo.today/api/prices";
const TTL_SECONDS = 60 * 60 * 12; // refresh at most twice a day

function jsonResponse(body, { maxAge = TTL_SECONDS } = {}) {
  return new Response(JSON.stringify(body), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": `public, max-age=${maxAge}`,
      "access-control-allow-origin": "*",
    },
  });
}

// Accept either an array of {date, fuel_type, price} or {prices:[{fuel_type,
// price}]}; pick the newest price per fuel type. Returns {PB95, ON, ...} numbers.
function parsePrices(data) {
  const rows = Array.isArray(data) ? data : Array.isArray(data?.prices) ? data.prices : [];
  const best = {};
  for (const r of rows) {
    const type = r.fuel_type;
    const price = parseFloat(r.price);
    if (!type || !isFinite(price)) continue;
    const when = r.date || "";
    if (!best[type] || when >= best[type].when) best[type] = { price, when };
  }
  const out = {};
  for (const t in best) out[t] = best[t].price;
  return out;
}

async function fetchFuel() {
  const res = await fetch(SOURCE, {
    headers: {
      // The API 403s default bot user-agents; present as a normal browser.
      "user-agent": "Mozilla/5.0 (compatible; vehicle-cost-calculator/1.0; +https://github.com/anotherk1t/vehicle-cost-calculator)",
      accept: "application/json",
    },
    cf: { cacheTtl: TTL_SECONDS, cacheEverything: true },
  });
  if (!res.ok) throw new Error(`upstream ${res.status}`);
  const p = parsePrices(await res.json());
  return {
    petrol: p.PB95 ?? FALLBACK.petrol,
    diesel: p.ON ?? FALLBACK.diesel,
    petrol98: p.PB98 ?? null,
    lpg: FALLBACK.lpg,
    electric: FALLBACK.electric,
    source: "paliwo.today",
    updated: new Date().toISOString().slice(0, 10),
    stale: false,
  };
}

async function handleFuel(request, ctx) {
  const cache = caches.default;
  const cacheKey = new Request(new URL("/api/fuel", request.url).toString(), request);
  const hit = await cache.match(cacheKey);
  if (hit) return hit;
  let body;
  try {
    body = await fetchFuel();
  } catch {
    body = { ...FALLBACK, source: "static", updated: null, stale: true };
  }
  const response = jsonResponse(body);
  // Only cache a real upstream answer, so a transient failure isn't pinned for 12h.
  if (!body.stale) ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/api/fuel") return handleFuel(request, ctx);
    return env.ASSETS.fetch(request); // everything else: serve the static site
  },
};
