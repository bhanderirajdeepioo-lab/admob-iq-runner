// 📝 Note edit (node --test): History's admin fix "📝 add or edit a note" on an older day, and the author's own edit on
// the open day. The old text is never lost (its row is only marked deleted, the log keeps both), and nobody edits a
// note that is not theirs (except an admin). All data synthetic (fake keys, example.test emails).
import test from "node:test";
import assert from "node:assert/strict";
import { setup, K, D0, D1, OWNER, TEAMMATE } from "./harness.js";
import { applyAction } from "../src/db.js";

const notes = (t) => t.db.q("SELECT id, day, app, text, who, deleted_by, deleted_at FROM rv_notes ORDER BY id");
const actions = (t) => t.db.q("SELECT * FROM rv_actions ORDER BY id");

test("admin: a note on an OLDER day is edited — the old row kept (marked deleted), the new text listed, logged as admin_fix", async () => {
  const t = await setup();
  const own = { token: t.tokens.owner };
  const add = await t.act({ d: D0, act: "note", app: K.b, note: "first text" }, own);
  assert.equal(add.status, 200);
  const n0 = add.json.notes[0];
  const r = await t.act({ d: D0, act: "note_edit", app: K.b, note_id: n0.id, note: "  better text  " }, own);
  assert.equal(r.status, 200, r.text);
  assert.equal(r.json.d, D0);
  assert.equal(r.json.app, K.b);
  assert.deepEqual(r.json.notes.map((x) => [x.text, x.who]), [["better text", OWNER]]);
  assert.notEqual(r.json.notes[0].id, n0.id, "the new text is a new row");
  assert.equal(r.json.state.st, "ok", "the state of the day is not touched");
  // the old row is still there, only marked deleted by the editor
  const rows = notes(t);
  assert.deepEqual(rows.map((x) => [x.text, x.deleted_by]), [["first text", OWNER], ["better text", null]]);
  // GET day: only the new text; the log has the edit (ref = the edited note, the new text, admin_fix)
  const day = await t.day(D0, own);
  assert.deepEqual(day.notes.map((x) => x.text), ["better text"]);
  const log = actions(t).filter((x) => x.act === "note_edit");
  assert.equal(log.length, 1);
  assert.equal(log[0].day, D0);
  assert.equal(log[0].ref, n0.id);
  assert.equal(log[0].note, "better text");
  assert.equal(JSON.parse(log[0].extra).admin_fix, 1);
  assert.ok(day.log.some((x) => x.act === "note_edit"));
  // the calendar still counts ONE note on that day
  const cal = (await t.get(`calendar?from=${D0}&to=${D1}`, own)).json.days;
  assert.equal(cal[D0].notes, 1);
});

test("older day: a teammate cannot edit (403 day_closed); open day: the author edits, another teammate cannot, an admin can", async () => {
  const t = await setup();
  const own = { token: t.tokens.owner };
  const old = (await t.act({ d: D0, act: "note", app: K.a, note: "old day note" }, own)).json.notes[0];
  const r0 = await t.act({ d: D0, act: "note_edit", app: K.a, note_id: old.id, note: "changed" });
  assert.equal(r0.status, 403);
  assert.equal(r0.json.error, "day_closed");

  // the open day: the teammate's own note
  const mine = (await t.act({ act: "note", app: K.c, note: "my note" })).json.notes[0];
  assert.equal(mine.who, TEAMMATE);
  const r1 = await t.act({ act: "note_edit", app: K.c, note_id: mine.id, note: "my note, fixed" });
  assert.equal(r1.status, 200, r1.text);
  assert.deepEqual(r1.json.notes.map((x) => x.text), ["my note, fixed"]);
  assert.equal(actions(t).at(-1).extra, null, "the open day is no admin fix");
  // someone else's note: another teammate → 403 not_author (nothing written); the admin → 200
  const before = actions(t).length;
  const r2 = await t.act({ act: "note_edit", app: K.c, note_id: r1.json.notes[0].id, note: "not mine" }, { token: t.tokens.team2 });
  assert.equal(r2.status, 403);
  assert.deepEqual(r2.json, { error: "forbidden", msg: "Ye note sirf jisne likha wo (ya admin) badal sakta hai", why: "not_author" });
  assert.equal(actions(t).length, before);
  const r3 = await t.act({ act: "note_edit", app: K.c, note_id: r1.json.notes[0].id, note: "admin wording" }, own);
  assert.equal(r3.status, 200);
  assert.deepEqual(r3.json.notes.map((x) => [x.text, x.who]), [["admin wording", OWNER]]);
});

test("note_edit validation: note_id and a non-empty note required; another day's / app's / a deleted note → 404", async () => {
  const t = await setup();
  const own = { token: t.tokens.owner };
  const n = (await t.act({ d: D0, act: "note", app: K.a, note: "x" }, own)).json.notes[0];
  for (const [body, field] of [
    [{ d: D0, act: "note_edit", app: K.a, note: "y" }, "note_id"],
    [{ d: D0, act: "note_edit", app: K.a, note_id: "1", note: "y" }, "note_id"],
    [{ d: D0, act: "note_edit", app: K.a, note_id: 0, note: "y" }, "note_id"],
    [{ d: D0, act: "note_edit", app: K.a, note_id: n.id, note: "   " }, "note"],
    [{ d: D0, act: "note_edit", app: K.a, note_id: n.id }, "note"],
  ]) {
    const r = await t.act(body, own);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.equal(r.json.field, field, JSON.stringify(body));
  }
  // the right id but another app / another day / unknown id
  assert.equal((await t.act({ d: D0, act: "note_edit", app: K.b, note_id: n.id, note: "y" }, own)).status, 404);
  assert.equal((await t.act({ d: D1, act: "note_edit", app: K.a, note_id: n.id, note: "y" }, own)).status, 404);
  assert.equal((await t.act({ d: D0, act: "note_edit", app: K.a, note_id: 99999, note: "y" }, own)).status, 404);
  // after ↩ undo the note is gone: an edit of it → 404, nothing comes back
  assert.equal((await t.act({ d: D0, act: "undo", app: K.a }, own)).status, 200);
  const r = await t.act({ d: D0, act: "note_edit", app: K.a, note_id: n.id, note: "y" }, own);
  assert.equal(r.status, 404);
  assert.deepEqual((await t.day(D0, own)).notes, []);
});

test("note_edit inside the batch: a note deleted after the check (an undo in between) → 409 note_gone, nothing written", async () => {
  const t = await setup();
  const own = { token: t.tokens.owner };
  const n = (await t.act({ d: D0, act: "note", app: K.a, note: "x" }, own)).json.notes[0];
  t.db.sqlite.exec(`UPDATE rv_notes SET deleted_by = 'someone', deleted_at = '2026-10-02T05:00:00.000Z' WHERE id = ${n.id}`);
  const before = { log: actions(t).length, notes: notes(t).length };
  await assert.rejects(
    applyAction(t.db, { act: "note_edit", d: D0, openDay: D1, app: K.a, note: "y", noteId: n.id, who: OWNER,
      at: "2026-10-02T05:01:00.000Z", label: "", extra: { admin_fix: 1 } }),
    (e) => e.status === 409 && e.extra && e.extra.why === "note_gone");
  assert.deepEqual({ log: actions(t).length, notes: notes(t).length }, before);
  assert.equal(notes(t)[0].deleted_by, "someone", "the earlier delete is left as it was");
});
