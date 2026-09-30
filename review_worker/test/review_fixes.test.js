// Review fixes (node --test): a decided whole-app 🚩 frees the card, decisions carry their REVIEW day, the admin
// view's "Band" list keeps 14 days, a page left open across the new day cannot write to yesterday, no framing.
import test from "node:test";
import assert from "node:assert/strict";
import { setup, makeIndex, K, D0, D1, D2 } from "./harness.js";

const actions = (t) => t.db.q("SELECT * FROM rv_actions ORDER BY id");

test("whole-app 🚩: ok / kal refused while it is open; once the admin decides it the card can be marked again", async () => {
  const t = await setup();
  const f = (await t.act({ act: "flag", app: K.a, note: "dekho" })).json.flags.find((x) => x.feature === null);
  assert.equal((await t.act({ act: "ok", app: K.a })).json.why, "flagged");
  // a FEATURE flag never blocks the card
  await t.act({ act: "flag", app: K.b, feature: "kamai" });
  assert.equal((await t.act({ act: "ok", app: K.b })).status, 200);

  for (const [decision, note] of [["theek", ""], ["kaam", "developer ko do"]]) {
    const u = decision === "theek" ? t : await setup();
    const id = decision === "theek" ? f.id
      : (await u.act({ act: "flag", app: K.a })).json.flags.find((x) => x.feature === null).id;
    const d = await u.decide({ flag_id: id, decision, note });
    assert.equal(d.status, 200, decision);
    assert.equal((await u.day()).states[K.a].st, "flag", "the state row stays as the record of the day");
    const ok = await u.act({ act: "ok", app: K.a });
    assert.equal(ok.status, 200, `${decision}: ${ok.text}`);
    assert.equal(ok.json.state.st, "ok");
    assert.equal((await u.act({ act: "kal", app: K.a })).json.state.st, "kal");
  }
  // a NEW whole-app flag on the same day blocks again
  await t.act({ act: "flag", app: K.a });
  assert.equal((await t.act({ act: "ok", app: K.a })).json.why, "flagged");
});

test("a decision records the REVIEW day it was made on (dec_day / done_day), not the IST clock date", async () => {
  const t = await setup({ index: makeIndex(D0) });
  const f = (await t.act({ d: D0, act: "flag", app: K.a, feature: "ads" })).json.flags[0];
  const k = await t.decide({ flag_id: f.id, decision: "kaam", note: "campaign dekho" });
  assert.deepEqual([k.json.flag.dec_day, k.json.flag.done_day], [D0, null]);
  const g = (await t.act({ d: D0, act: "flag", app: K.b, feature: "kamai" })).json.flags[0];
  await t.decide({ flag_id: g.id, decision: "theek" });
  // both decided while D0 was open, but at 01:30 IST on D1 (before the 09:00 snapshot) — the clock says D1
  t.db.sqlite.exec(`UPDATE rv_flags SET dec_at = '2026-10-01T20:00:00.000Z' WHERE id IN (${f.id}, ${g.id})`);
  t.setIndex(makeIndex(D1));
  const done = await t.decide({ flag_id: f.id, decision: "done" });
  assert.deepEqual([done.json.flag.dec_day, done.json.flag.done_day], [D0, D1]);
  assert.deepEqual(actions(t).filter((x) => x.act === "decide").map((x) => x.day), [D0, D0, D1]);

  // History (open day D2): D1 lists the flag closed on D1 (done) but NOT the one closed on review day D0
  t.setIndex(makeIndex(D2));
  const h1 = (await t.get(`day?d=${D1}`, { token: t.tokens.owner })).json;
  assert.deepEqual(h1.flags.map((x) => x.id), [f.id]);
  const h0 = (await t.get(`day?d=${D0}`, { token: t.tokens.owner })).json;
  assert.deepEqual(h0.flags.map((x) => x.id).sort(), [f.id, g.id].sort());
});

test("open day: flags closed in the last 14 review days stay listed (admin view \"Band\"), older ones drop out", async () => {
  const t = await setup();
  const f = (await t.act({ act: "flag", app: K.a, feature: "ads" })).json.flags[0];
  const b = await t.decide({ flag_id: f.id, decision: "band", note: "rewarded ad unit band karo" });
  assert.equal(b.json.flag.dec_day, D1);
  const at = (day) => makeIndex(D2, { open_day: day, today_ist: day });
  for (const [day, listed] of [[D2, true], ["2026-10-16", true], ["2026-10-17", false]]) {
    t.setIndex(at(day));
    const s = (await t.get(`day?d=${day}`)).json;
    assert.equal(s.flags.some((x) => x.id === f.id), listed, day);
    // the action response for that app follows the same rule
    const r = await t.act({ d: day, act: "note", app: K.a, note: "n" });
    assert.equal(r.status, 200, r.text);
    assert.equal(r.json.flags.some((x) => x.id === f.id), listed, `action ${day}`);
  }
  // a withdrawn flag is never carried to a later day
  t.setIndex(makeIndex(D1));
  const w = (await t.act({ act: "flag", app: K.c, feature: "health" })).json.flags[0];
  await t.act({ act: "unflag", flag_id: w.id });
  t.setIndex(makeIndex(D2));
  assert.equal((await t.get(`day?d=${D2}`)).json.flags.some((x) => x.id === w.id), false);
});

test("live: true (the page's Aaj view) on a day that is no longer open → 409 day_moved + the new open day, even for an admin", async () => {
  const t = await setup();          // open day D1; D0 is an older snapshot
  const own = { token: t.tokens.owner };
  for (const opt of [{}, own]) {
    const r = await t.act({ d: D0, act: "ok", app: K.a, live: true }, opt);
    assert.equal(r.status, 409);
    assert.deepEqual(r.json, { error: "conflict", msg: "Naye din ke cards aa gaye — upar “Kholo” dabao", why: "day_moved",
      open_day: D1 });
  }
  const bulk = await t.act({ d: D0, act: "bulk_ok", apps: [K.a], live: true }, own);
  assert.equal(bulk.json.why, "day_moved");
  assert.equal(actions(t).length, 0, "nothing written");
  // the open day itself is fine with live: true; History's admin correction (no live) still works
  assert.equal((await t.act({ act: "ok", app: K.a, live: true })).status, 200);
  const fix = await t.act({ d: D0, act: "ok", app: K.a }, own);
  assert.equal(fix.status, 200);
  assert.equal(JSON.parse(actions(t).at(-1).extra).admin_fix, 1);
  assert.equal((await t.act({ act: "ok", app: K.b, live: "yes" })).json.field, "live");
});

test("every API response forbids framing (X-Frame-Options DENY + CSP frame-ancestors 'none')", async () => {
  const t = await setup();
  for (const r of [await t.get("me"), await t.get("me", { token: null }), await t.get(`day?d=${D1}`),
    await t.act({ act: "ok", app: K.a })]) {
    assert.equal(r.headers.get("x-frame-options"), "DENY");
    assert.equal(r.headers.get("content-security-policy"), "frame-ancestors 'none'");
  }
});
