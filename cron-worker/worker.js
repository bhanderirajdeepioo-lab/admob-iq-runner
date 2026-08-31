// Cloudflare Worker — reliably triggers the AdMob IQ refresh every hour.
// GitHub's own scheduled workflows get throttled/skipped (2–6h real gaps), so instead
// this Worker's Cron Trigger fires on time and pokes the workflow_dispatch API.
//
// Setup: add a secret GH_TOKEN (classic PAT with repo + workflow scope) and a Cron Trigger
// (e.g. "17 * * * *" = hourly). See cron-worker/README.md.

async function trigger(env) {
  const url = "https://api.github.com/repos/bhanderirajdeepioo-lab/admob-iq-runner/actions/workflows/refresh.yml/dispatches";
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": "token " + env.GH_TOKEN,
      "Accept": "application/vnd.github+json",
      "User-Agent": "admob-iq-cron-worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  const ok = res.status === 204;            // GitHub returns 204 on success
  console.log(ok ? "refresh triggered OK" : ("dispatch failed " + res.status + " " + (await res.text())));
  return res.status;
}

export default {
  // fires on the cron schedule (reliable, unlike GitHub's own schedule)
  async scheduled(event, env, ctx) { ctx.waitUntil(trigger(env)); },
  // visiting the Worker URL also triggers a refresh — handy to test it works
  async fetch(request, env, ctx) {
    const st = await trigger(env);
    return new Response(st === 204 ? "AdMob IQ refresh triggered OK" : ("failed: HTTP " + st), { status: 200 });
  },
};
