# admob-iq-cron — reliable hourly refresh

GitHub scheduled workflows are throttled (real gaps 2–6h), so this Cloudflare Worker
triggers the refresh on time instead.

## Setup (Cloudflare dashboard — no CLI needed)
1. Workers & Pages -> Create -> Workers -> Create Worker -> name it `admob-iq-cron` -> Deploy.
2. Edit code -> paste `worker.js` -> Save and Deploy.
3. Worker -> Settings -> Variables and Secrets -> Add -> **Secret**:
   name `GH_TOKEN`, value = a GitHub classic PAT with **repo + workflow** scope.
4. Worker -> Settings -> Triggers -> Cron Triggers -> Add -> `17 * * * *` (hourly).
5. Test: open the Worker's `*.workers.dev` URL -> should say "refresh triggered OK",
   and a run appears in the runner repo's Actions within a few seconds.

That's it — data now refreshes every hour, independent of GitHub's schedule.
