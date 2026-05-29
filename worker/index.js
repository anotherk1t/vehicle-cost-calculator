// Private-preview gate for the static site.
//
// The site is hosted as Workers Static Assets; this Worker runs *before* asset
// serving (assets.run_worker_first = true in wrangler.jsonc) and enforces HTTP
// Basic Auth. Any username is accepted; the password is checked against the
// SITE_PASSWORD secret (set with `wrangler secret put SITE_PASSWORD` — it never
// lives in code or git). Remove this Worker (or set run_worker_first = false)
// to make the site public.

const REALM = "mobility-cost-pl (private preview)";

function unauthorized() {
  return new Response("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"` },
  });
}

// Constant-time compare so a wrong password can't be recovered via timing.
function safeEqual(a, b) {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  if (ab.length !== bb.length) return false;
  let diff = 0;
  for (let i = 0; i < ab.length; i++) diff |= ab[i] ^ bb[i];
  return diff === 0;
}

export default {
  async fetch(request, env) {
    const expected = env.SITE_PASSWORD;
    if (!expected) {
      return new Response("Site password not configured.", { status: 500 });
    }
    const header = request.headers.get("Authorization") || "";
    if (header.startsWith("Basic ")) {
      let decoded = "";
      try {
        decoded = atob(header.slice(6));
      } catch {
        decoded = "";
      }
      const sep = decoded.indexOf(":"); // user:pass — username ignored
      const pass = sep === -1 ? "" : decoded.slice(sep + 1);
      if (safeEqual(pass, expected)) {
        return env.ASSETS.fetch(request); // authenticated → serve the static site
      }
    }
    return unauthorized();
  },
};
