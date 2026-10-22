"""🧊 The cohort cube — GA4 ad revenue by ACTIVITY day × INSTALL day × COUNTRY, from the app's GA4 history start to
today, kept for good (owner, 20 Oct 2026: "jitna purana app utna date" — the ROI section's install-day table goes on
past D30 in 30-day columns up to the app's age; real data only, nothing trimmed, the full history).

Why this read (measured on the real properties by fetch/ga4_cohort_country_probe.py, report in the private repo):
  * runReport dimensions [date, firstSessionDate] WITHOUT countryId answers install days only back to about 15 months
    (GA4's horizon for that shape): on an old app such a read misses much of the revenue of the users installed
    earlier — so it is never used past D30;
  * the SAME read WITH countryId answers every install day back to the app's start (the whole block total on the small
    and medium apps);
  * on the biggest app a 30-day block comes back with "(other)" rows (firstSessionDate and countryId both "(other)")
    holding a large share of the revenue, while ONE activity day a query comes back with no "(other)" at all.

The read — runReport v1beta on the app's Android stream (ga4.stream_filter), USD, keepEmptyRows false, every page
(report_all with gu.UNI_PAGE_ROWS: never cut), no firstSessionDate filter (only a split part's, step 3):
    dimensions [date, firstSessionDate, countryId], metrics [activeUsers, totalAdRevenue]
adaptive, per range of activity days:
  1. a block of BLOCK (30) days in one call; when any row has "(other)" (or a date that is not one), the answer was cut
     (truncated) or any page's metadata says dataLossFromOtherRow or sampling, the block's answer is dropped and
  2. each day of it is read alone; when a day still has "(other)" (or the same flags),
  3. that day is split (split_read), again and again while a part of it still has "(other)" (owner, 21 Oct 2026:
     "revenue cross check kro country wise, admob ke sath verify kro" — on the biggest apps one split left a large
     share of some months' revenue in "(other)"). A part is a filter on countries (an in-list, or "not in" a list) and
     on install days (an in-list, or "not in" a list); a part whose answer still has "(other)" — a row, or only GA4's
     dataLossFromOtherRow (an in-list filter DROPS the "(other)" row: its revenue is gone from the answer, the flag
     alone says so — ga4_uninstall's Q-C note) — or was sampled / cut is read again as two parts that PARTITION it
     (every row of it in exactly one of them, never in both; the part's own answer kept until both are in):
       * by countries while it holds more than one: an in-list → its two halves; "every country but E" → the biggest
         named countries of its answer up to half its rows (the most rows — the cardinality GA4 folds into "(other)" —
         then revenue, then code) in an in-list H, and "every country but E + H" (countries GA4 hid in "(other)",
         "(not set)" and empty stay in that one: never in a list, so never lost);
       * one country left (or none named): by install days (firstSessionDate) — an in-list → its two halves (by date,
         each half about half the rows); no list → the oldest named install days of its answer up to half its rows in
         an in-list H, and "every install day but H" (a "(not set)" install day, one GA4 hid: in that one);
       * one country and one install day: it cannot be split — what stays "(other)" in it is measured loss.
     The part with the most "(other)" revenue goes first (a flagged one with no row: the most rows first); at the day's
     call cap (DAY_CAP calls, HOT_CAP for a hot day) no more parts are read: whatever is STILL "(other)" is the day's
     measured loss ("ol", in "loss"): kept as such, never spread ("cap" 1 on the day: a deeper split could have read
     more). A split whose two halves name no row their part had not (GA4 rolled the rows into "(other)" before the
     filters — then no filter ever names them) ends the day's split at once ("fu": 3 calls, not the cap; the part as it
     was, its "(other)" the measured loss). A final part still flagged dataLossFromOtherRow with no "(other)" row →
     ONE more call, the day's own total (dimension date only, no filter: one row — nothing to roll up or drop): what
     it holds beyond every part's rows (past ½ micro a row + 1 ppm of rounding) is "(other)" GA4 hid — added to the
     day's t, loss and ol ("hd" on the record; the log's "hidden"), never missing unrecorded; that total sampled, cut,
     flagged dataLossFromOtherRow itself or with a row that is not a date (nothing to measure by), or parts holding
     more than it → "fl". A day not final yet (a hot day) is never measured so: GA4 still adds to it between the
     calls, a gap would be revenue that came in during the read — its hidden part is "fl" (no total call). A Stop
     (the run's budget, the property's quota, MAX_CALLS) in the middle of a day keeps nothing of it: the day is not
     folded and is read again, whole, next run (first in it). A Stop counts as the day's cut only when the day had
     the run's whole allowance: its app's FIRST read of the run (never one that started with what the walk, the hot
     days or the other days left) in an app that started with ≥ FULL_SHARE of the run's budget left (never one after
     another app of its property, or one that waited for a worker), after ≥ MIN_CAP calls of it and not the app's
     own call cap: a day cut that way CUT_TRIES times gets a smaller cap — the calls a run gave it less one, then
     half that … never below MIN_CAP (the old one-level split) — so a day too costly for one run can never stall the
     walk (its loss stays measured, "cap" 2: under its full cap a read again could take more — the repair's queue
     counts it). The walk ("cut") and the hot days ("hcut") keep their own cut memory: a hot day's smaller cap never
     follows it into its final read (its memory goes once the day is final).
  A range at least as long as one that needed step 2 goes to step 2 straight away for HEAVY_KEEP activity days ("heavy":
  its block call would only be dropped again); then the block is tried once more.
Per row: countryId "(not set)" / empty → cc "--"; a firstSessionDate that is not a date ("(other)", "(not set)"), a
countryId "(other)" or an install day after the activity day → the day's loss (micros; st "loss" only then). GA4's
thresholding, sampling, a cut answer, or a flag still on the final answer with no "(other)" row to measure it by → the
day's "fl" (st stays ok / split: a flag is not a measured loss; the page marks ≈ with no direction; nothing guessed).

Stored in the private repo, data/ga4_cube/<key>/ — by ACTIVITY month; a month file never changes once its days are all
folded (a folded day is never read or folded again by the walk; only the repair below replaces a whole month, once per
split version):
    <YYYY-MM>.json.gz = {"v", "stream_id",
      "days": {D: {"st": ok|split|loss, "rows", "loss", "t", "fl", "via": block|day|split, "at",     the ledger
                   "sv" (the split's version: SPLIT_V; absent = 1, the one-level split before 21 Oct 2026), "ol" (the
                   part of "loss" that is "(other)": what a deeper split could still read), "n" (GA4 calls the day
                   took, its total included; 0 = a share of one block call), "cap" (1: the day's cap left "(other)" a
                   deeper split could read; 2: a smaller cap did — a day cut run after run)}}
      "b": {X: {j: {W: micros}}}          ALL countries summed, ages L ≥ 31 in 30-day buckets j = (L − 31) // 30 + 1
                                          (bucket j = ages 30j+1 … 30j+30: the step into D(30 + 30j)); W = the Monday of
                                          the activity day (engine.value._mon: the week of the AdMob ÷ GA4 scale k)
      "c": {cc: {X: {j: micros}}}         per country, the same buckets, summed over this activity month
      "e": {cc: {X: [u0, r0, r1 … r30]}}  per country, ages 0 … 30 day by day (u0 = activeUsers at age 0 = the
                                          country's installs; r in micros; trailing zeros trimmed)
      "t": {D: micros}                    every row of the day (the loss share's denominator)
      "loss": {D: micros}                 what stayed "(other)" / had no install day (days with some only)
      "rep": {"sv", "at", "ol0", "loss0", "t0"}}   only on a month the repair rebuilt (below): when, and what it held
    <YYYY-MM>.rep.json.gz — the repair's copy of that month while it is being built (the same format; never read by
      the build: months() takes YYYY-MM.json.gz only)
    hot.json.gz = {"v", "app_id", "package", "property_id", "stream_id", "time_zone", "hs", "from", "next", "done",
      "walk_at", "hot_at", "hot_today", "hot_cyc" ([when, property day] of a round of the hot days a Stop cut: the next
      run reads only its days not read since), "heavy", "cut" / "hcut" (the final / hot day a Stop cut as the run's first
      read: {"D", "n" calls it had, "k" times}), "rep" (the repair's state, below), "d": {D: {the ledger's fields + "b",
      "c", "e" of that one day (+ "hd" / "fu" / "dp": the split's depth when past its first level)}}}
— the head (progress) and the NON-FINAL days (today − 2 … today), each replaced when read again. The ROI build reads only
a hot day's ledger and "b"; its "c" / "e" are kept in the same shapes as the months for a per-country / D0 … D30 view
(nothing reads them yet — the biggest app's ≈ 3 hot days of them are most of this file).
X = install day (firstSessionDate), D = activity day (date), both YYYY-MM-DD in the property's time zone; j, W as text.

Progress — ONE cursor, "next": every activity day before it is folded, from a read made when it was already FINAL
(≤ the property's today − FINAL_LAG). A run walks from the cursor to the final edge (the first walk = the backfill
from the history start; a catch-up after a Stop, a pause, failed runs or a new day is the same walk), folding each day
ONCE (a day already in its month's ledger is skipped, never re-read), the cursor moving after each day; "done" once a
walk reached the final edge (the build uses the cube only from then on: the columns come in one go). Then, every
REFRESH_HOURS or on a new property day, today − 2 … today again (hot: never folded; such a day is read once more when
final and folded then; a hot copy of a day that is final now is dropped at the start of every run — a hole until the
walk folds it, never a read made while it was filling standing in for the final one). A history start that moves back
restarts the walk from it and clears "done" (the build waits for it again). A month file on disk that cannot be read
(a damaged gzip, a cut copy), is not this format or is another stream's is never written over with only the days after
the cursor: the cursor goes back to that month's first day and the whole month is read again ("months read again" in
the log). The walk holds at most two months in memory (a month it left is written and let go; folded days are passed
a month at a time). Month files are written as the walk leaves them and at the end, the head after them (it never runs
ahead of the months). The property quota gate of ga4_firstopen.App, MAX_CALLS a run per app, its own budget
(GA4_CUBE_BUDGET_SEC); properties side by side (WORKERS); on a property the app that waited longest goes first and an
app cut off by the budget goes after the others next run (a long backfill never starves a light app) — but an app whose
FIRST read a Stop cut with less than the run's whole allowance ("late": not that day's cut) goes first next run, and
its property starts first (the day gets a whole allowance: its cut counts or it is read). Switched by
GA4_CUBE (off: nothing read, written or printed; the ROI build leaves the store unread). Never raises; never prints
(log_line: counts only).

The repair (repair()) — months folded before the deeper split, whose days still carry "(other)" loss, are read again
and REPLACED whole. Only once the walk reached the final edge in the run and the hot days are read, with what the run
has left (at most REPAIR_CALLS calls started a run, MAX_CALLS and the budget as always). One month at a time:
  * the queue: every month file of the app (one at a time) with recoverable loss — the days whose ledger "sv" is older
    than SPLIT_V and whose "ol" > 0 (an older ledger without "ol": a "split" day's loss; a "block" / "day" day had no
    "(other)" row, its loss is install days that are not dates — no split reads those), and the days of this split
    with "cap" 2 folded after the month's last repair of this split (a day the repair itself read so is never queued
    again: no month is repaired again and again) — biggest share of the month's revenue first, the more recent month
    first on a tie; then the months whose only reason is a one-level "split" day GA4 flagged with no "(other)" row (its
    in-list part may have hidden some, by how much unknown: share 0, after every measured one); made once per SPLIT_V
    and again every RESCAN_DAYS while it is empty (a month folded by an older copy of this code elsewhere); a month
    whose file is gone (or holds no day any more) has nothing to read: its copy dropped, the next month next run;
  * the month's every day is read again, day by day (never a block: a month with "(other)" only comes back with it
    again) with the deeper split, into its copy <YYYY-MM>.rep.json.gz, kept across runs (a Stop keeps the days read; a
    day the Stop cut is read again, whole); a day is started only when the run's calls AND time left fit what a day
    needs (calls: its calls a day so far, DAY_CAP + 1 before the first; time: the most calls a day took, "m", × the
    app's seconds a call — this run's, else the last measured, "s") — checked before every day (a budget Stop in a
    started day throws its calls away, a day not started costs nothing); the month file itself is never touched
    meanwhile (the build reads it as it was);
  * once the copy holds every day the month file holds (a day the walk folds into the current month meanwhile is read
    into the copy too), the copy becomes the month file ("rep": what the old one held), the head is written (even in a
    run that made no call) and only then the copy is removed (a run killed before the head finds the copy whole and
    does the same again; a head left naming a month with nothing left to read reads nothing of it again). Its days now
    carry "sv" = SPLIT_V: never queued again unless SPLIT_V goes up (a still deeper split) and their "ol" is still > 0.
  head "rep" = {"sv", "scan" (when the queue was made), "q": [[YYYY-MM, share]], "k" (the month being rebuilt), "old"
  {"ol", "loss", "t"} (what it held), "at", "c" / "n" / "m" (calls / days of this repair, the most calls a day),
  "cut" (the cut memory of its reads), "s" (the app's seconds a GA4 call, last measured), "log": [[month, "(other)"
  micros before, after, the month's revenue, when]] (the last LOG_KEEP)}.

q — the WHOLE read of ages 31 … 420 (owner, 21 Oct 2026: real data only, nothing GA4 dropped left out). GA4 folds the
country "(other)" BEFORE any filter, so no split above gets it back (measured: the repair read nothing back). But one
activity day with dimension firstSessionDate ONLY, no filter, every page (q_read: the install-day fetch's own per-day
read, ga4_uninstall.rep_iday_qb) comes back whole up to install age 427 on that day (measured on several apps: no
"(other)", data loss, sampling or thresholding in any such read). Its ages 31 … QL (420) in the cube's buckets 1 … QJ
(13) are the All rows' cells there (the ROI build: roi_build._late); bucket 14 (ages 421 … 450) crosses the 427-day
horizon and stays on the cube. Per day: "q" {X: {j: micros}}, "qt" (ages 0 … 420, micros), "qn" (micros of rows GA4
gave no install day: "(not set)", not a date, after the day — real rows of the whole read, in no install day: kept as
their size, never a reason to drop the day), "qx" (the oldest install age the read returned: a shrinking window shows),
"qs" "ok" — or "fl" (an empty q) on an "(other)" install day (GA4 folded rows: not whole), GA4's dataLossFromOtherRow,
sampling, thresholding or a cut answer — and "qr" (rows). A folded day of nothing (no revenue, no loss, no flag in the
cube's ledger: q_need) is never read (its q would be empty; the build needs none for it).
SETTLED (22 Oct 2026, measured on the real properties: every read of a day ≥ 5 days old came back "ok", reads of days
2–4 days old "fl" on several apps — install ages far past 427 in the answer —, while older days in the same hour were
"ok"): a q read of activity day D is final only when made ≥ Q_SETTLE (5) property days after D (q_ripe / q_settled).
A folded day is read only once it has settled (it waits in "p": no read before — nor by the history fill's queue: a
day not settled yet there goes to "p"). A stored "fl" is not final while (q_due) its read was made before D settled —
read again once it has, the new answer REPLACING it (an "fl" holds no cell: nothing to take out) — or it is a settled
"fl" read again fewer than Q_RETRY (2) times ("rt"), each ≥ Q_GAP_HOURS (24) after the last; then it is final (its
week on the cube's cells for good). An "ok" made once D settled is final (whole: GA4 flagged nothing; never replaced —
its cells are in the month's sums). An "ok" made before D settled (q_early: only q files of before 22 Oct 2026 —
measured: such reads too named install ages past 427) is not: its cells are summed per week, so q_rescan takes its
WEEK out of the q file (the week's cells and "ok" days; its "fl" days hold none and stay), those days back in "p" —
read again once settled (no Q_V change: the file keeps its format, only that week is read again; counted "q early").
The build takes the same rule from q_due: a week held by a not-final "fl" is waiting ("qwait"), by a final one on the
cube ("qfl"); a week taken out is waiting (a day without q). Stored:
    <YYYY-MM>.q.json.gz = {"v", "stream_id", "days": {D: {"qs", "qt", "qn", "qx", "qr", "at", "rt" (a settled "fl"
      read again this many times; absent = 0 — q files of before 22 Oct are the same format: no Q_V change)}}, "q": {X:
      {j: {W: micros}}}} — the same shape as the month's "b" (j ≤ QJ only); never read by months() (its name is not
      YYYY-MM.json.gz) and never touched by the repair; a day in it is never read again unless it is an "fl" not final;
    a hot day's record in hot.json.gz gets "q" ({X: {j: {W: micros}}}), "qt", "qn", "qx", "qs", "qr" — read in the SAME
      run as its cube read (the same moment: GA4 still adds to a hot day), else none (the build uses its cube cells);
    head "qh" = {"p": [days folded without a q yet (or whose week q_rescan took out), oldest first — read once
      settled], "todo": [[YYYY-MM, its measured "(other)" share, days without q, loss micros]] (the history fill's
      queue), "scan" (when it was made), "r": [[D, when it is due ("…Z"), its week's measured loss micros]] (the
      stored "fl" days not final: kept by every q_put, made from the q files by q_rescan when there is none and every
      RESCAN_DAYS), "rs" (when that was made)}.
Reads (GA4_CUBE_Q_CALLS, Q_CALLS; 0 = q off: no q read at all, and the build uses the cube's own cells as before;
GA4_CUBE_Q_USE=false, Q_USE: the reads go on, the build ignores every q file — a rollback that keeps the data):
  * in step_app, after the hot days (q_fwd): the hot days this run read (each hot round: their rows need it; an "fl"
    there blocks nothing — the hot copy goes at the fold and the folded day waits for its settled read), then up to
    Q_FWD days of "p" that have settled (a newer one stays in "p") — the app's call cap ends it (the rest stays in
    "p"), a budget / quota Stop goes on up (what was read is kept); any other error ends q for the app this run
    (counted: "q errors"), never the app's run;
  * after EVERY app's run (refresh_all's second round, with what the run's budget left — never a property's walk or
    hot days later): the history fill (q_fill), at most Q_CALLS calls and Q_SEC seconds a run over all apps (never past
    the budget), the app's call cap as always — the apps with re-reads due on lossy weeks first, then those with
    settled days in "p" (a day not settled yet is no work: every app has a few), then the apps whose queue (+ lossy
    weeks due a re-read, each week once) holds the most measured loss, so the lossy apps fill first; per app first
    the stored "fl" days due a read again on weeks with measured loss (the biggest week loss first: a whole read there
    takes it back), then the settled days of "p", then the other re-reads due, then the queue's months (made once by
    q_scan from the month files — no GA4 call —, again every RESCAN_DAYS while it is empty; an app not scanned yet is
    counted apart, "q unscanned", never in "q left"): the months with loss first (the biggest share first), then every
    other month newest first, each month's days without q oldest first (only those that have settled: a newer one
    goes to "p" — the current month's newest days are always there). A Stop keeps every q day read; an error ends
    that app's fill (counted). The log: "q settling" (days in "p" not settled yet), "q reread" / "q recovered" (stored
    "fl" days read again in the run / of them "ok" now), "q fl waiting" (stored "fl" days still to be read again),
    "q early" ("ok" days taken out with a week read before it settled: read again).

Users (u, 22 Oct 2026 — owner: "retention data already ham track nahi kar rahe he?"): GA4's own activeUsers come in
every answer above (METS) — the cube kept only age 0 ("e" u0), q none. Now kept, from the answers already received
(no call of their own), in files of their own next to the cube's (GA4_CUBE_U, U_ON; off: nothing kept, read or written
— the cube as without it); the revenue files (months, q files, hot.json.gz, the head) are never touched by them:
  * the cube's reads (walk, hot days, repair): per activity day D and country, users at install ages 0 … 30 and every
    30th day from 60 (u_age: the days of the 30-day columns) — rows GA4 gave no install day or country ("(other)",
    "(not set)" install day, one after the day) are the day's "ou" (measured, never spread to any cell); a day GA4
    flagged (sampling, thresholding, a cut answer) or that hid "(other)" under an in-list ("hd": its revenue measured by
    the day's total, users have none) is "fl" (how many are missing: unknown);
  * q's whole no-country reads (q_fwd, the history fill, its re-reads): users of every install day at ages 60, 90 …
    420 (UQ_AGES; the read is whole to 427) — a read that is not whole ("fl"): no users (unknown).
Stored (data/ga4_cube/<key>/, never read as a month or q file — the names differ):
    <YYYY-MM>.u.json.gz = {"v": U_V, "stream_id",
      "c": {D: {"u": {cc: [users at ages 0 … 30]}, "w": {cc: {age: users}}, "ou", "fl", "at", "by": fold|fill|rep}},
      "q": {D: {"s": ok|fl, "at", "u": [users at ages 60, 90 … 420] (only when "ok")}}}
      install day X = D − age; a country / age not named on a day kept = 0 users (the read had no row of it); a day
      not kept = unknown. "c" from the walk's fold (the final read) — the fill or the repair only add a day without one;
      "q" from a settled whole read: an "ok" is never replaced, an "fl" by the next whole read of the day;
    u.json.gz (the users' head) = {"v", "stream_id", "d": {D: {"c": …, "q": …}} the hot days' users, each part with the
      "at" of the cube read it came with (the build takes it only beside that very read; dropped with the head's hot
      day), "qs" / "cs": the fills' queues {"todo": [[YYYY-MM, days to read]], "scan", "hk" (cs: days left read alone
      after a block came back with "(other)")}}.
The history (refresh_all, after q's fill; each its own calls and seconds a run over every app, the run's budget and the
app's call cap as always; the app whose fill read longest ago first; a Stop keeps every day read; an error ends that
app's fill, counted; queues made from the files — no call — and again every RESCAN_DAYS while empty):
  * All users (u_fill_q, GA4_CUBE_U_CALLS / GA4_CUBE_U_SEC, U_CALLS 120 / U_SEC 20): one whole no-country read (q_read,
    ~1 token) per folded activity day ≥ history start + U_FROM (150: younger days hold only ages the install-day file
    already has — 60 / 90 / 120), with a row, settled, no whole read's users kept — and not a day q itself will read
    (q on, the day needs one, no final q record: that read keeps them); newest first. Only its users are kept.
  * country users (u_fill_c, GA4_CUBE_U_C_CALLS / GA4_CUBE_U_C_SEC / GA4_CUBE_U_C_CAP, 120 / 20 / 3): the cube's own
    read again (read_range: a block of up to BLOCK days, else each day alone and its split under UC_CAP, no day total)
    of every folded day after the history start with a row and no users kept; newest first; only its users kept (what
    stays "(other)" is the day's "ou", flagged).
Fill time (one run an hour): All users ≈ (app age − 150) days per app at ≈ 60–120 light calls a run over every app;
country users ≈ app age / 30 block calls on a light app (a run or two), a day alone + 2 split calls on a heavy one
(≈ 4–6 s a call: ≈ 1–2 days a run in UC_SEC 20 s — raise GA4_CUBE_U_C_SEC to go faster, inside the budget).
Cost: the backfill ≈ app age / 30 block calls on a light app (rows a call ≈ 30 × a day's (install day, country) rows),
and on a heavy one about one call per activity day (+ 2 per part split, + one block try every HEAVY_KEEP days) —
measured on the biggest app ≈ 70 GA4 tokens and 4–6 s a day call, so ≈ 25 calls a run in the 150 s budget (the walk
goes on next run). A day that still has "(other)": 1 + 2 × (parts split) calls (+ 1, its total, only when a part
hides "(other)") — when GA4 rolls rows up per answer, a day r times over its limit needs about 2r − 1 or more (the
halves stop as soon as a part comes back whole; synthetic: 5 calls at 1.5×, 9 at 3×, 25 at 8×); when GA4 rolls them
up before the filters, 3 (the first split names nothing more) + 1; never more than DAY_CAP (24, one run's budget) + 1
— which of the two GA4 does the log's "futile" / "hidden" counts will show (not measured yet). After the walk, a day:
the new final day + the hot window (≤ 3 × (HOT_CAP + 1) calls, a round a Stop cut going on with its unread days) every
6 hours and at the property's midnight. The repair of a month ≈ 30 day reads × the calls a day takes (≈ 30 × 4–10 =
120–300 on the biggest app): ≤ REPAIR_CALLS (env GA4_CUBE_REPAIR_CALLS; 0 = off, the default) started a run, and only with a day's room (calls and time) left →
about 4–10 runs a month, the biggest loss first. A run never makes more than MAX_CALLS (60) calls an app: the final
day (≤ 25, on a new day) and the hot days (≤ 39, every 6 h) go first, the repair only with what they left (most
hourly runs: they read nothing, the repair gets its 30); what does not fit is read next run. q: one light call a day
(≤ 428 rows) — going forward the day that settled + the hot days of a round (≤ 1 + 3 a run, inside MAX_CALLS), the
history once (≤ Q_CALLS calls and ≤ Q_SEC seconds a run over every app, only from what the budget left after every
app's walk and hot days; none once filled) + a stored "fl" read again at most 1 + Q_RETRY times (the measured "fl"
days: the few days read 2–4 days after them). GA4 tokens stay under the property's quota floors (the App's gate stops
every read of the property before them).
"""
import heapq
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .. import ga4_probe
from ..db import write_json_gz_stable
from . import ga4
from . import ga4_audience as gaud
from . import ga4_firstopen as gf
from . import ga4_uninstall as gu
from .ga4_firstopen import Stop

DIR = "ga4_cube"
V = 1
LAGS = 31                           # ages 0 … 30 day by day ("e"); from 31 on in 30-day buckets ("b", "c")
STEP = 30                           # bucket j = ages 30j+1 … 30j+30
BLOCK = 30                          # activity days a block call
SPLIT_V = 2                         # the split's version (ledger "sv"): 1 one country level, 2 recursive (21 Oct 2026)
DAY_CAP = 24                        # GA4 calls a final day's split may take (then what is still "(other)" is its loss):
                                    # one run's budget (≈ 25 calls of 4–6 s in 150 s) — a day fits the run it starts
HOT_CAP = 12                        # … a hot day's (read again every 6 hours, never folded: its final read is kept)
MIN_CAP = 3                         # the smallest cap a day cut again and again gets (the one-level split's 3 calls)
CUT_TRIES = 2                       # runs a day may be cut by a Stop (after ≥ MIN_CAP calls of it) before its cap
                                    # shrinks
FULL_SHARE = 0.9                    # … a Stop counts only in an app that started with ≥ this share of the run's budget
REPAIR_CALLS = int(os.environ.get("GA4_CUBE_REPAIR_CALLS") or 0)    # calls a run may start repair days with (a started
                                    # day finishes or is cut); 0 = the repair is off. Off by default: on real GA4 the
                                    # country "(other)" is folded BEFORE filters (a split names no row its root had
                                    # not), so a repair read gets nothing back — measured on its first real run
RESCAN_DAYS = 7                     # the repair's (and q's) queue made again (while empty) after this many days
QJ = 13                             # q: buckets 1 … 13 = ages 31 … 420 from the whole no-country day read
QL = LAGS - 1 + STEP * QJ           # 420: the oldest age q keeps (the read is whole to 427; bucket 14 = 421 … 450)
QDIMS = ("firstSessionDate",)
Q_V = 1
QSUF = ".q.json.gz"
Q_CALLS = int(os.environ.get("GA4_CUBE_Q_CALLS") or 120)    # the history fill's GA4 calls a run, over every app (0 =
                                    # q off: no q read at all, the build uses the cube's own cells). A light read (≤ 428
                                    # rows, ~1 token, ~0.5–1 s with the 0.2 s pause): Q_SEC ends the round first on most
                                    # runs (≈ 60–120 calls in 20 s, WORKERS properties side by side); the cap only
                                    # bounds a fast run. The fill (≈ one read per folded day with revenue, once: the 7
                                    # lossy apps' ≈ 3.9k first, then the rest) ≈ 100–200 runs; nothing after that
Q_SEC = float(os.environ.get("GA4_CUBE_Q_SEC") or 20)      # the history fill's seconds a run (from the end of every
                                    # app's walk and hot days, never past the cube's budget): a run gets at most this
                                    # much longer, and only while the history is not filled
Q_APP_CALLS = int(os.environ.get("GA4_CUBE_Q_APP_CALLS") or 0)   # the history fill's own GA4 calls an app a run
                                    # (on top of what its walk / hot days used; 0 = the app's MAX_CALLS bounds the
                                    # fill too, as before) — the fill's day reads are ~1 token each
Q_USE = (os.environ.get("GA4_CUBE_Q_USE") or "true").strip().lower() != "false"   # false: the build ignores q files
                                    # (reads go on): q rolled back on the page without deleting a byte
Q_FWD = 7                           # settled days folded without a q read, read in an app's own run (step_app), at most
Q_SETTLE = int(os.environ.get("GA4_CUBE_Q_SETTLE") or 5)   # a q read of activity day D is final only when made ≥ this
                                    # many property days after D (measured 22 Oct 2026: reads 2–4 days after the day
                                    # came back "fl" on several apps — install ages far past 427 —, every older day's
                                    # "ok"): q_fwd / the fill read a folded day only once it settled; a stored "fl" from
                                    # a read made before that is read again once it has (the new answer replaces it)
Q_RETRY = int(os.environ.get("GA4_CUBE_Q_RETRY") or 2)     # a settled "fl" read again at most this many times ("rt"),
                                    # ≥ Q_GAP_HOURS apart; then final (its week on the cube's cells for good)
Q_GAP_HOURS = 24.0                  # … at least this long after its last read
# u — GA4's own users (activeUsers) of the reads above, kept next to the cube (module doc, "Users")
U_ON = (os.environ.get("GA4_CUBE_U") or "true").strip().lower() != "false"     # false: no users kept, no u file read
                                    # or written, no users fill (the cube's reads and files exactly as without it)
U_USE = (os.environ.get("GA4_CUBE_U_USE") or "true").strip().lower() != "false"   # false: the build ignores every u
                                    # file and the install-day file's users past D30 (the page's file as before)
U_V = 1
USUF = ".u.json.gz"                 # <YYYY-MM>.u.json.gz: an activity month's users (never a month or a q file)
UHEAD = "u.json.gz"                 # the users' head: the hot days' users + the two fills' queues
UQ_AGES = tuple(range(2 * STEP, QL + 1, STEP))      # 60, 90 … 420: All users of the whole no-country read ("q" "u")
U_FROM = min(a for a in UQ_AGES if a not in gu.ULAGS)   # 150: the first 30-day column's age the install-day file
                                    # (fetch.ga4_uninstall ULAGS: 60 / 90 / 120 / 180 / 270) does not hold — the All
                                    # users fill reads activity days from history start + this on
U_CALLS = int(os.environ.get("GA4_CUBE_U_CALLS") or 120)    # the All users fill's GA4 calls a run over every app (0 =
                                    # off): q's light whole read (~1 token, ≤ 428 rows), one per activity day
U_SEC = float(os.environ.get("GA4_CUBE_U_SEC") or 20)      # … its seconds a run (from its own start, inside the budget)
UC_CALLS = int(os.environ.get("GA4_CUBE_U_C_CALLS") or 120)    # the country users fill's GA4 calls a run over every
                                    # app (0 = off): the cube's own read again (a block of BLOCK days, else a day alone
                                    # and its split under UC_CAP)
UC_SEC = float(os.environ.get("GA4_CUBE_U_C_SEC") or 20)   # … its seconds a run
UC_CAP = max(1, int(os.environ.get("GA4_CUBE_U_C_CAP") or MIN_CAP))   # GA4 calls a day the country users fill may take
                                    # (the cube's split, one level at 3: on real GA4 a split names nothing more — the
                                    # futile rule ends it there anyway); what stays "(other)" is the day's "ou"
LOG_KEEP = 24                       # repaired months kept in the head's "rep" "log"
REP = ".rep.json.gz"                # a month's copy while the repair builds it
HEAVY_KEEP = 90                     # activity days a range goes day by day after a block of its length needed it
FINAL_LAG = 3                       # an activity day is final once ≤ the property's today − 3 (as ga4_cohort)
REFRESH_HOURS = 6.0                 # the hot days (today − 2 … today) read again
MAX_CALLS = 60                      # per app per run (the walk goes on next run)
BUDGET_SEC = 150
RETRY_HOURS = 3.0
WORKERS = 3                         # properties read side by side (each its own quota)
DIMS = ("date", "firstSessionDate", "countryId")
METS = ("activeUsers", "totalAdRevenue")
OTHER = "(other)"
NO_CC = "--"                        # countryId "(not set)" / empty
HOT = "hot.json.gz"
LEDGER = ("st", "rows", "loss", "t", "fl", "via", "at", "sv", "ol", "n", "cap")
LEDGER_OPT = ("fu", "hd", "dp")       # kept on a day only when the read set them (why a split stopped, hidden micros, depth)
F_OTHER, F_SMP, F_CUT, F_THR = 1, 2, 4, 8       # GA4's flags on an answer
RETRY = F_OTHER | F_SMP | F_CUT                 # … that a smaller read can avoid


def _d(s):
    return date.fromisoformat(s)


def _real(s):
    """GA4's YYYYMMDD → YYYY-MM-DD when it is a real date ("(other)", "(not set)", junk → None)."""
    s = str(s or "")
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
    except ValueError:
        return None


def _mon(d):
    return d - timedelta(days=d.weekday())


def bucket(L):
    """Age L ≥ 31 → its 30-day bucket j (1: ages 31 … 60, 2: 61 … 90, …)."""
    return (L - LAGS) // STEP + 1


def _days(a, b):
    out = []
    while a <= b:
        out.append(a)
        a += timedelta(days=1)
    return out


# ── the read ────────────────────────────────────────────────────────────────────────────────────────────────────────
def body(a, b, dims=DIMS):
    """Activity days a … b: every install day and country (no firstSessionDate filter)."""
    return {"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}],
            "dimensions": ga4._dim(*dims), "metrics": ga4._dim(*METS), "currencyCode": "USD", "keepEmptyRows": False}


def cc_in(ccs):
    return ga4._in_list("countryId", sorted(ccs))


def cc_not(ccs):
    return {"notExpression": cc_in(ccs)}


def x_in(xs):
    """firstSessionDate in-list of install days (YYYY-MM-DD → GA4's YYYYMMDD)."""
    return ga4._in_list("firstSessionDate", sorted(x.replace("-", "") for x in xs))


def _flags(ga, rows):
    """GA4's flags on the last report_all: any page's dataLossFromOtherRow / sampling / thresholding, a cut answer."""
    f = 0
    for m in getattr(ga, "last_metas", None) or [getattr(ga, "last_meta", None) or {}]:
        if isinstance(m, dict):
            f |= (F_OTHER if m.get("dataLossFromOtherRow") else 0) | (F_SMP if m.get("samplingMetadatas") else 0) \
                 | (F_THR if m.get("subjectToThresholding") else 0)
    if hasattr(ga, "truncated") and ga.truncated(rows):
        f |= F_CUT
    return f


def _other(rows):
    """Any row GA4 rolled into "(other)" (or whose activity day is not a date)?"""
    for r in rows:
        if OTHER in (r.get("firstSessionDate"), r.get("countryId")) or not _real(r.get("date")):
            return True
    return False


def _cc(r):
    cc = str(r.get("countryId") or "")
    return NO_CC if cc in ("", "(not set)") else cc


def _new():
    acc = {"b": {}, "c": {}, "e": {}, "t": 0, "loss": 0, "rows": 0, "oth": 0, "ol": 0}
    if U_ON:                                    # users of the same rows (u): per country by age, and those GA4 gave
        acc["uu"], acc["ou"] = {}, 0            # no install day / country
    return acc


def u_age(L):
    """An install age whose users a country keeps: 0 … 30 day by day, then every 30th day from 60 (the days of the
    30-day columns)."""
    return 0 <= L < LAGS or (L >= 2 * STEP and L % STEP == 0)


def _add(acc, Dd, W, X, Xd, r):
    """One row of activity day Dd (W: its Monday) into the day's accumulator; X / Xd: its install day (None: not a
    date)."""
    v = int(round(float(r.get("totalAdRevenue") or 0) * 1e6))
    acc["rows"] += 1
    acc["t"] += v
    cc = _cc(r)
    if OTHER in (r.get("firstSessionDate"), r.get("countryId")):
        acc["oth"] += 1
        acc["ol"] += v
    L = (Dd - Xd).days if Xd else -1
    uu = acc.get("uu")
    if Xd is None or cc == OTHER or L < 0:
        acc["loss"] += v
        if uu is not None:                      # users GA4 gave no install day / country: their size, never spread
            acc["ou"] += int(r.get("activeUsers") or 0)
        return
    if uu is not None and u_age(L):
        n = int(r.get("activeUsers") or 0)
        if n:
            ul = uu.setdefault(cc, {})
            ul[L] = ul.get(L, 0) + n
    if L < LAGS:
        u = int(r.get("activeUsers") or 0) if L == 0 else 0
        if not (u or v):
            return
        arr = acc["e"].setdefault(cc, {}).setdefault(X, [])
        if len(arr) < L + 2:
            arr.extend([0] * (L + 2 - len(arr)))
        arr[0] += u
        arr[L + 1] += v
    elif v:
        j = str(bucket(L))
        w = acc["b"].setdefault(X, {}).setdefault(j, {})
        w[W] = w.get(W, 0) + v
        c = acc["c"].setdefault(cc, {}).setdefault(X, {})
        c[j] = c.get(j, 0) + v


def _trim(arr):
    n = len(arr)
    while n and not arr[n - 1]:
        n -= 1
    return arr[:n]


def _group(rows, day=None):
    """Rows → {D: accumulator} (a row without a real activity day: `day`'s, when the read was of one day)."""
    out, ds, xs = {}, {}, {}
    for r in rows:
        raw = r.get("date")
        if raw not in ds:
            D = _real(raw) or (day.isoformat() if day else None)
            ds[raw] = (D, _d(D), _mon(_d(D)).isoformat()) if D else None
        if ds[raw] is None:
            continue
        D, Dd, W = ds[raw]
        raw = r.get("firstSessionDate")
        if raw not in xs:
            X = _real(raw)
            xs[raw] = (X, _d(X) if X else None)
        if D not in out:
            out[D] = _new()
        _add(out[D], Dd, W, xs[raw][0], xs[raw][1], r)
    return out


def _rec(acc, via, fl, now_iso, info=None):
    """A day's accumulator → its record: the ledger's fields + "b", "c", "e". info: split_read's (its leaves' flag, its
    calls, the cap); None: a block's share (a block is kept only with no "(other)" and none of RETRY's flags)."""
    acc = acc or _new()
    flag = info["flag"] if info is not None else bool(fl & (F_SMP | F_CUT | F_THR))
    e = {}
    for cc, xs in acc["e"].items():
        for X, arr in xs.items():
            a = _trim(arr)
            if a:
                e.setdefault(cc, {})[X] = a
    st = "loss" if acc["loss"] else ("split" if via == "split" else "ok")      # flagged only: "fl", never "loss"
    rec = {"st": st, "rows": acc["rows"], "loss": acc["loss"], "t": acc["t"], "fl": 1 if flag else 0, "via": via,
           "at": now_iso, "sv": SPLIT_V, "ol": acc["ol"], "n": info["calls"] if info else 0,
           "cap": info["cap"] if info else 0, "b": acc["b"], "c": acc["c"], "e": e}
    if "uu" in acc:                             # the day's users (U_ON): taken off the record before anything stores
        rec["u"] = _uc(acc)                     # it (Cube.fold / u_hot_c / u_put) — never in a revenue file
    return rec


def _uc(acc):
    """A day's users → {"u": {cc: [users at ages 0 … 30]} (trailing zeros trimmed), "w": {cc: {age: users}} (every
    30th day from 60), "ou": users of rows GA4 gave no install day or country ("(other)", "(not set)" install day, after
    the day): measured, in no cell}. A country (or age) not named: 0 users that day (the read had no row of it)."""
    u, w = {}, {}
    for cc, ls in acc["uu"].items():
        a = [0] * LAGS
        for L, n in ls.items():
            if L < LAGS:
                a[L] = n
            else:
                w.setdefault(cc, {})[str(L)] = n
        a = _trim(a)
        if a:
            u[cc] = a
    return {"u": u, "w": w, "ou": acc["ou"]}


def _ufl(rec):
    """A day's users flagged: GA4 sampled / thresholded / cut its read, or hid "(other)" under an in-list (the revenue
    measured by the day's total — "hd" —, users have no such total): how many users are missing is unknown."""
    return 1 if rec.get("fl") or rec.get("hd") else 0


# ── the recursive split of one activity day ─────────────────────────────────────────────────────────────────────────
# A part = (cin, cout, xin, xout): countries in cin (a frozenset; None: no in-list) else not in cout; install days
# (YYYY-MM-DD) in xin (None: no in-list) else not in xout. The day itself = (None, ∅, None, ∅).
def _filters(p):
    cin, cout, xin, xout = p
    ex = []
    if cin is not None:
        ex.append(cc_in(cin))
    elif cout:
        ex.append(cc_not(cout))
    if xin is not None:
        ex.append(x_in(xin))
    elif xout:
        ex.append({"notExpression": x_in(xout)})
    return ex


def _stats(rows, key):
    """{named value: [rows, revenue]} of one dimension in an answer — a country: not "(other)" / "(not set)" / empty;
    an install day: a real date (YYYY-MM-DD)."""
    out = {}
    for r in rows:
        v = _cc(r) if key == "countryId" else _real(r.get(key))
        if not v or v in (NO_CC, OTHER):
            continue
        s = out.setdefault(v, [0, 0.0])
        s[0] += 1
        s[1] += float(r.get("totalAdRevenue") or 0)
    return out


def _half(order, st, keep_one):
    """The first values of `order` until they hold half its rows (a value the answer did not name counts 1 row) —
    at least one; keep_one: at least one left for the other half."""
    w = [max(1, (st.get(v) or (0,))[0]) for v in order]
    tot, cum, n = sum(w), 0, 0
    while n < len(order) and (n == 0 or 2 * cum < tot):
        cum += w[n]
        n += 1
    return order[:min(n, len(order) - 1) if keep_one else n]


def _kids(p, rows, dims):
    """A part whose answer still has "(other)" → the two parts that partition it (module doc, step 3); None: it cannot
    be split (one country and one install day, or nothing named to split by)."""
    cin, cout, xin, xout = p
    if "countryId" in dims and (cin is None or len(cin) > 1):
        st = _stats(rows, "countryId")
        if cin is not None:
            order = sorted(cin, key=lambda c: (-(st.get(c) or (0, 0.0))[0], -(st.get(c) or (0, 0.0))[1], c))
            h = frozenset(_half(order, st, True))
            return [(h, frozenset(), xin, xout), (cin - h, frozenset(), xin, xout)]
        order = sorted((c for c in st if c not in cout), key=lambda c: (-st[c][0], -st[c][1], c))
        if order:
            h = frozenset(_half(order, st, False))
            return [(h, frozenset(), xin, xout), (None, cout | h, xin, xout)]
    st = _stats(rows, "firstSessionDate")
    if xin is not None:
        if len(xin) < 2:
            return None
        h = frozenset(_half(sorted(xin), st, True))
        return [(cin, cout, h, frozenset()), (cin, cout, xin - h, frozenset())]
    order = sorted(x for x in st if x not in xout)
    if not order:
        return None
    h = frozenset(_half(order, st, False))
    return [(cin, cout, h, frozenset()), (cin, cout, None, xout | h)]


def _orev(rows):
    return sum(float(r.get("totalAdRevenue") or 0) for r in rows
               if OTHER in (r.get("firstSessionDate"), r.get("countryId")) or not _real(r.get("date")))


def _named(rows):
    """Rows GA4 kept by name (not "(other)", a real activity day)."""
    return sum(1 for r in rows if OTHER not in (r.get("firstSessionDate"), r.get("countryId")) and _real(r.get("date")))


def _micros(rows):
    return sum(int(round(float(r.get("totalAdRevenue") or 0) * 1e6)) for r in rows)


def _hidden(rows, fl):
    """GA4 says it rolled rows into "(other)" but no "(other)" row shows (an in-list filter drops that row)."""
    return bool(fl & F_OTHER) and not _other(rows)


def day_total(ga, D):
    """Activity day D's whole ad revenue (micros): dimension date only and no filter — one row, nothing GA4 could roll
    into "(other)" or a filter could drop. None: nothing to measure by — GA4 sampled or cut that answer, flagged it
    dataLossFromOtherRow (GA4 can flag a read with no filter too: ga4_audience's re-asks) or gave a row whose day is
    not a date."""
    rows = ga.report_all(body(D, D, ("date",)), page_rows=gu.UNI_PAGE_ROWS)
    if _flags(ga, rows) & RETRY or _other(rows):
        return None
    return _micros(rows)


def split_read(ga, D, cap=DAY_CAP, xs=None, dims=DIMS, total=None):
    """Activity day D through the recursive split (module doc, step 3) → (rows of every final part, info {"calls",
    "parts", "depth", "cap" (1: the cap left "(other)" a deeper split could read), "fl" (every part's GA4 flags), "flag"
    (a flag with nothing to measure it by: sampling / thresholding / a cut answer, dataLossFromOtherRow on a part with
    no "(other)" row when the day's total is not read or could not be, or parts holding more than that total), "hid"
    (micros the day's total holds beyond every part's rows: "(other)" GA4 hid under an in-list — 0: none, or not
    measured), "futile" (1: a split named no row its part had not — filters read no more of this day)}). xs: the
    install days (YYYY-MM-DD) the read is held to (an in-list; None: every one); dims: without countryId only install
    days split; total(ga, D): the day's true total in micros, or None (read once, only when a final part is flagged
    "(other)" with no "(other)" row — a call past the cap; None given: never read, such a part is a flag). Raises
    Stop: nothing of the day kept."""
    c0, seq, leaves, heap = ga.calls, 0, [], []
    info = {"calls": 0, "parts": 0, "depth": 0, "cap": 0, "fl": 0, "flag": False, "hid": 0, "futile": 0}
    held = False                                                # a hidden-"(other)" part the cap kept from a split

    def read(p):
        ex = _filters(p)
        rows = ga.report_all(body(D, D, dims), extra=ex or None, page_rows=gu.UNI_PAGE_ROWS)
        return rows, _flags(ga, rows)

    def put(p, rows, fl, depth, why):
        nonlocal seq
        if _other(rows) or fl & why:
            seq += 1                                            # the most "(other)" revenue first; a hidden one (no
            heapq.heappush(heap, (-_orev(rows), -len(rows), seq, depth, p, rows, fl))   # row): the most rows first
        else:
            leaves.append((rows, fl))
    root = (None, frozenset(), frozenset(xs) if xs is not None else None, frozenset())
    rows, fl = read(root)
    put(root, rows, fl, 0, RETRY)
    while heap:
        _, _, _, depth, p, rows, fl = heapq.heappop(heap)
        kids = _kids(p, rows, dims)
        if kids and ga.calls - c0 + len(kids) > cap:            # the cap: no more parts read
            info["cap"] |= int(_other(rows))
            held = held or _hidden(rows, fl)
            kids = None
        if not kids:
            leaves.append((rows, fl))                           # what is still "(other)" in it: the day's loss
            continue
        got = [read(k) for k in kids]                           # the part's rows kept until both halves are in
        still = fl & F_SMP and all(f & F_SMP for _, f in got)   # sampled, and both halves sampled again: a
        if still or not fl & (F_SMP | F_CUT) and sum(_named(r) for r, _ in got) <= _named(rows):   # split never
            #                                                     gets past GA4's sampling (a cut part still splits)
            info["futile"] = 1                                  # the halves named no row the part had not (GA4 rolls
            leaves.append((rows, fl))                           # rows into "(other)" before a filter): no part read
            leaves.extend((e[5], e[6]) for e in heap)           # by a filter will — the part as it was, the others as
            heap.clear()                                        # they are; what is "(other)" in them: measured loss
            break
        del rows
        for k, (r, f) in zip(kids, got):
            put(k, r, f, depth + 1, RETRY)
        info["depth"] = max(info["depth"], depth + 1)
    measured = False
    if total is not None and any(_hidden(r, f) for r, f in leaves):
        T = total(ga, D)                                        # GA4 hid "(other)" somewhere: the day's own total
        if T is not None:
            measured = True
            s, n = sum(_micros(r) for r, _ in leaves), sum(len(r) for r, _ in leaves)
            tol = n // 2 + 1 + T // 1000000                     # rounding: ½ micro a row, 1 ppm of the total
            if T - s > tol:
                info["hid"] = T - s
                info["cap"] |= int(held)
            elif s - T > tol:
                info["flag"] = True                             # the parts hold more than the day: no measure
    out = []
    for rows, f in leaves:
        out.extend(rows)
        info["fl"] |= f
        info["flag"] = info["flag"] or bool(f & (F_SMP | F_CUT | F_THR)) or (_hidden(rows, f) and not measured)
    info.update(calls=ga.calls - c0, parts=len(leaves))
    return out, info


def read_day(ga, D, now_iso, cap=DAY_CAP, full=None, hot=False):
    """One activity day alone (steps 2 and 3 of the module doc) → its record ("(other)" GA4 hid, measured by the day's
    total, in its t / loss / ol; "hd" / "fu" / "dp" on the record only when there is one: the hidden micros / a futile
    split / the split's depth past its first level). full: the cap a day of its kind gets — read with less (a day cut
    run after run), "cap" 2 when the cap left "(other)" (a full read could take more of it). hot: a day not final yet —
    never measured by its total (GA4 still adds to it between the calls: the gap would be revenue that came in during
    the read, not "(other)"), a part that hid "(other)" is "fl". Raises Stop (nothing of the day kept)."""
    rows, info = split_read(ga, D, cap, total=None if hot else day_total)
    acc = _group(rows, D).get(D.isoformat()) or _new()
    del rows
    if info["hid"]:
        for f in ("t", "loss", "ol"):
            acc[f] += info["hid"]
    if info["cap"] and full is not None and cap < full:
        info["cap"] = 2
    rec = _rec(acc, "split" if info["depth"] else "day", info["fl"], now_iso, info)
    if info["hid"]:
        rec["hd"] = info["hid"]
    if info["futile"]:
        rec["fu"] = 1
    if info["depth"] > 1:
        rec["dp"] = info["depth"]
    return rec


def _cap_of(cut, cap):
    """A day's cap: `cap`, or — cut by a Stop in CUT_TRIES runs or more — what a run gave it less one, halved for every
    further cut, never below MIN_CAP."""
    if isinstance(cut, dict) and int(cut.get("k") or 0) >= CUT_TRIES:
        return max(MIN_CAP, min(cap, (int(cut.get("n") or 0) - 1) >> (int(cut["k"]) - CUT_TRIES)))
    return cap


def _read_day(ga, D, now_iso, mem, cap, key="cut", hot=False):
    """read_day with the cut memory mem[key] ("cut": a final day of the walk, "hcut": a hot day — never one for the
    other: a hot day's smaller cap never follows it into its final read; the repair: its own state's "cut"). A Stop
    counts as the day's cut only when the day had the run's whole allowance — its app's FIRST read of the run (never
    one started with what the walk, the hot days or other days left) in an app that started with ≥ FULL_SHARE of the
    run's budget left (ga.full, set by refresh_all: never an app that went after another of its property or waited
    for a worker) —, after ≥ MIN_CAP calls of it, and not the app's call cap: {"D", "n" the most calls a run gave it,
    "k" how many times}."""
    k, c0 = D.isoformat(), ga.calls
    cut = mem.get(key) if isinstance(mem.get(key), dict) and mem[key].get("D") == k else None
    try:
        rec = read_day(ga, D, now_iso, _cap_of(cut, cap), full=cap, hot=hot)
    except Stop as e:
        n = ga.calls - c0
        if c0 == 0 and n >= MIN_CAP and str(e) != "calls":
            if getattr(ga, "full", True):
                mem[key] = {"D": k, "n": max(n, int((cut or {}).get("n") or 0)),
                            "k": int((cut or {}).get("k") or 0) + 1}
            else:
                ga.late = True                              # not its cut: its app goes first next run (refresh_all)
        raise
    if cut is not None:
        mem.pop(key, None)
    return rec


def _skip_block(head, a, n):
    hv = head.get("heavy")
    try:
        return bool(hv) and n >= int(hv["n"]) and 0 <= (a - _d(hv["at"])).days < HEAVY_KEEP
    except (KeyError, TypeError, ValueError):
        return False


def read_range(ga, a, b, head, now_iso, cap=DAY_CAP, key="cut", hot=False):
    """Activity days a … b → (D, record) in day order, adaptive (see the module doc). A generator: a Stop between its
    calls keeps every day it yielded. head: where the heavy and cut memories live; key: the cut memory's (the walk's
    "cut", the hot days' "hcut"); hot: days not final yet (read_day)."""
    n = (b - a).days + 1
    if n > 1 and not _skip_block(head, a, n):
        rows = ga.report_all(body(a, b), page_rows=gu.UNI_PAGE_ROWS)
        fl = _flags(ga, rows)
        if not (_other(rows) or fl & RETRY):
            hv = head.get("heavy")
            if hv and n >= int(hv.get("n") or 0):           # a block as long as the heavy one came back whole
                head.pop("heavy", None)
            got = _group(rows)
            del rows
            for D in _days(a, b):
                yield D, _rec(got.get(D.isoformat()), "block", fl, now_iso)
            return
        del rows
        head["heavy"] = {"at": a.isoformat(), "n": n}
    for D in _days(a, b):
        yield D, _read_day(ga, D, now_iso, head, cap, key, hot)


# ── q: the whole no-country read of one activity day (module doc) ──────────────────────────────────────────────────
def q_read(ga, D):
    """Activity day D, dimension firstSessionDate only, no filter, every page → {"q": {X: {j: micros}} (ages 31 … QL in
    buckets 1 … QJ), "qt" (micros of ages 0 … QL), "qn" (micros GA4 gave no install day: "(not set)", not a date, after
    D — real rows of a whole read, in no install day: their size, never a reason to drop the day), "qx" (the oldest
    install age returned; None: no dated row), "qs" "ok" | "fl", "qr" (rows)}. "fl", with an empty q: an "(other)"
    install day (GA4 folded rows into it) or GA4's dataLossFromOtherRow / sampling / thresholding / a cut answer — the
    day is not whole (its weeks stay on the cube's cells). Ages past QL (421 … 427) are left to the cube's bucket 14.
    Raises Stop."""
    rows = ga.report_all(body(D, D, QDIMS), page_rows=gu.UNI_PAGE_ROWS)
    bad = bool(_flags(ga, rows) & (RETRY | F_THR))
    q, qt, qn, qx = {}, 0, 0, None
    qu = [0] * len(UQ_AGES) if U_ON else None   # the same answer's users at ages 60, 90 … 420 (u: the All rows' mu)
    for r in rows:
        v = int(round(float(r.get("totalAdRevenue") or 0) * 1e6))
        if r.get("firstSessionDate") == OTHER:
            bad = True
            continue
        X = _real(r.get("firstSessionDate"))
        L = (D - _d(X)).days if X else -1
        if L < 0:
            qn += v
            continue
        qx = L if qx is None else max(qx, L)
        if L > QL:
            continue
        qt += v
        if qu is not None and L >= 2 * STEP and L % STEP == 0:
            qu[L // STEP - 2] += int(r.get("activeUsers") or 0)
        if L >= LAGS and v:
            j = str(bucket(L))
            e = q.setdefault(X, {})
            e[j] = e.get(j, 0) + v
    out = {"q": {} if bad else q, "qt": qt, "qn": qn, "qx": qx, "qs": "fl" if bad else "ok", "qr": len(rows)}
    if qu is not None:
        out["qu"] = None if bad else qu         # not whole: its users unknown too
    return out


def q_need(led):
    """A folded day (its ledger) needs a q read: it has revenue, loss or a GA4 flag — a day of nothing does not (its
    whole read is empty too; the build takes such a day as whole without one)."""
    return isinstance(led, dict) and bool(int(led.get("t") or 0) or int(led.get("loss") or 0) or led.get("fl"))


def _qw(q, D):
    """A day's q {X: {j: micros}} → {X: {j: {W: micros}}} (W: the day's Monday — the shape of the cube's "b")."""
    W = _mon(_d(D)).isoformat()
    return {X: {j: {W: v} for j, v in js.items()} for X, js in q.items()}


def _zone(tz):
    try:
        return ZoneInfo(tz) if tz else timezone.utc
    except Exception:
        return timezone.utc


def _pday(t, tz=None):
    """A moment (a datetime, or the store's "…Z" text) → the property's day then (tz: its time zone, None = UTC);
    None: not a moment."""
    if isinstance(t, str):
        t = gu._parse_iso(t)
    if not isinstance(t, datetime):
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(_zone(tz)).date()


def q_ripe(D, today):
    """Activity day D has settled by the property's day `today`: a q read of it now is final (Q_SETTLE)."""
    return today is not None and (today - _d(D)).days >= Q_SETTLE


def q_settled(D, at, tz=None):
    """A q read of D made at `at` (the record's "at") was made once D had settled (an unknown time: not)."""
    return q_ripe(D, _pday(at, tz))


def q_early(rec, D, tz=None):
    """A stored "ok" of day D from a read made before D settled (an unknown read time: not settled) — not final
    (Q_SETTLE: measured, such a read can name install ages GA4 has not settled yet, past 427, with no flag). No read is
    made before a day settles now: only q files of before 22 Oct 2026 hold one. Its cells are summed into its week's
    (no day's own), so q_rescan takes the WEEK out of the month's q file (every cell of it and its "ok" days; its "fl"
    days hold no cell and stay) and puts those days back in "p": read again once settled, the week whole again."""
    return isinstance(rec, dict) and rec.get("qs") == "ok" and not q_settled(D, rec.get("at"), tz)


def q_due(rec, D, tz=None):
    """A stored q record of day D → when it is to be read again (UTC "…Z"), None: never (final). "ok" (or not a
    record): never read again here (an "ok" read before D settled: q_early — its week taken out by q_rescan, never
    replaced in place). "fl" from a read made before D settled: the start of the property's day D + Q_SETTLE (its read
    was not final yet). A settled "fl": its read + Q_GAP_HOURS while it was read again fewer than Q_RETRY times
    ("rt"), then final. The same rule for the fill (what to read) and the build (waiting vs on the cube's cells for
    good)."""
    if not isinstance(rec, dict) or rec.get("qs") == "ok":
        return None
    if not q_settled(D, rec.get("at"), tz):
        d = _d(D) + timedelta(days=Q_SETTLE)
        return gu._now_iso(datetime(d.year, d.month, d.day, tzinfo=_zone(tz)))
    if int(rec.get("rt") or 0) >= Q_RETRY:
        return None
    at = rec["at"] if isinstance(rec["at"], datetime) else gu._parse_iso(rec["at"])
    return gu._now_iso(at + timedelta(hours=Q_GAP_HOURS))


def q_final(rec, D, tz=None):
    """A stored q record of D is never read again ("ok", or a settled "fl" read again Q_RETRY times)."""
    return q_due(rec, D, tz) is None


# ── the store ───────────────────────────────────────────────────────────────────────────────────────────────────────
def app_dir(data_dir, app_id):
    return os.path.join(data_dir, DIR, gu.file_key(app_id))


def month_path(data_dir, app_id, k):
    return os.path.join(app_dir(data_dir, app_id), k + ".json.gz")


def hot_path(data_dir, app_id):
    return os.path.join(app_dir(data_dir, app_id), HOT)


def _month_ok(s, stream_id):
    return (isinstance(s, dict) and s.get("v") == V and str(s.get("stream_id") or "") == str(stream_id or "")
            and all(isinstance(s.get(f), dict) for f in ("days", "b", "c", "e", "t", "loss")))


def load_head(data_dir, app_id):
    """The app's head + hot days (None: no cube, or not of this format)."""
    s = gu.load_store(hot_path(data_dir, app_id))
    return s if isinstance(s, dict) and s.get("v") == V and isinstance(s.get("d"), dict) else None


def months(data_dir, app_id, stream_id):
    """The app's month files of THIS stream, oldest first → (YYYY-MM, file) one at a time (a generator: the build folds
    a month and lets it go)."""
    folder = app_dir(data_dir, app_id)
    try:
        names = sorted(f for f in os.listdir(folder)
                       if len(f) == 15 and f.endswith(".json.gz") and f[4] == "-" and f[:4].isdigit())
    except OSError:
        return
    for f in names:
        s = gu.load_store(os.path.join(folder, f))
        if _month_ok(s, stream_id):
            yield f[:7], s


def _empty_month(stream_id):
    return {"v": V, "stream_id": stream_id, "days": {}, "b": {}, "c": {}, "e": {}, "t": {}, "loss": {}}


def q_path(data_dir, app_id, k):
    return os.path.join(app_dir(data_dir, app_id), k + QSUF)


def _q_ok(s, stream_id):
    return (isinstance(s, dict) and s.get("v") == Q_V and str(s.get("stream_id") or "") == str(stream_id or "")
            and isinstance(s.get("days"), dict) and isinstance(s.get("q"), dict))


def load_q(data_dir, app_id, stream_id, k):
    """Month k's q file of THIS stream (None: none, unreadable, or another stream's)."""
    s = gu.load_store(q_path(data_dir, app_id, k))
    return s if _q_ok(s, stream_id) else None


def _empty_q(stream_id):
    return {"v": Q_V, "stream_id": stream_id, "days": {}, "q": {}}


def u_path(data_dir, app_id, k):
    return os.path.join(app_dir(data_dir, app_id), k + USUF)


def uhead_path(data_dir, app_id):
    return os.path.join(app_dir(data_dir, app_id), UHEAD)


def _u_ok(s, stream_id, keys):
    return (isinstance(s, dict) and s.get("v") == U_V and str(s.get("stream_id") or "") == str(stream_id or "")
            and all(isinstance(s.get(f), dict) for f in keys))


def load_u(data_dir, app_id, stream_id, k):
    """Month k's users file of THIS stream (None: none, unreadable, or another stream's / format)."""
    s = gu.load_store(u_path(data_dir, app_id, k))
    return s if _u_ok(s, stream_id, ("q", "c")) else None


def load_uhead(data_dir, app_id, stream_id):
    """The users' head of THIS stream (None: none, unreadable, or another stream's / format)."""
    s = gu.load_store(uhead_path(data_dir, app_id))
    return s if _u_ok(s, stream_id, ("d",)) else None


def _empty_u(stream_id):
    return {"v": U_V, "stream_id": stream_id, "q": {}, "c": {}}


def _empty_uhead(stream_id):
    return {"v": U_V, "stream_id": stream_id, "d": {}}


def _uq(got, at):
    """A whole no-country read's users record: {"s": its qs, "at", "u": users at UQ_AGES (only when "ok")}."""
    r = {"s": got["qs"], "at": at}
    if got["qs"] == "ok" and isinstance(got.get("qu"), list):
        r["u"] = list(got["qu"])
    return r


def _merge(mo, k, rec):
    """Day k's record into a month (its b / c / e added, its t / loss / ledger set) — the caller makes sure it is not
    there yet."""
    for X, js in (rec.get("b") or {}).items():
        bx = mo["b"].setdefault(X, {})
        for j, ws in js.items():
            bj = bx.setdefault(j, {})
            for W, v in ws.items():
                bj[W] = bj.get(W, 0) + v
    for cc, xs in (rec.get("c") or {}).items():
        cm = mo["c"].setdefault(cc, {})
        for X, js in xs.items():
            cx = cm.setdefault(X, {})
            for j, v in js.items():
                cx[j] = cx.get(j, 0) + v
    for cc, xs in (rec.get("e") or {}).items():
        em = mo["e"].setdefault(cc, {})
        for X, arr in xs.items():
            cur = em.get(X) or []
            if len(cur) < len(arr):
                cur = cur + [0] * (len(arr) - len(cur))
            em[X] = _trim([a + (arr[i] if i < len(arr) else 0) for i, a in enumerate(cur)])
    mo["t"][k] = rec.get("t") or 0
    if rec.get("loss"):
        mo["loss"][k] = rec["loss"]
    mo["days"][k] = {f: rec.get(f) for f in LEDGER}
    mo["days"][k].update({f: rec[f] for f in LEDGER_OPT if rec.get(f)})


def _oloss(led, rep_at=None):
    """A folded day's "(other)" micros a read again could still take (0: none):
      * read with an older split (sv < SPLIT_V): "ol" when the ledger has it; an older ledger: a "split" day's loss (a
        "block" / "day" day had no "(other)" row: its loss is install days that are not dates, which no split reads);
      * read with this split but under a smaller cap than a day's (cap 2: a day cut run after run) — only when folded
        after the month's last repair of this split (rep_at; a day the repair itself read so stays as it is: a month is
        repaired once for what the walk folded, never again and again)."""
    if not isinstance(led, dict):
        return 0
    if int(led.get("sv") or 1) >= SPLIT_V:
        if int(led.get("cap") or 0) == 2 and (rep_at is None or str(led.get("at") or "") > rep_at):
            return int(led.get("ol") or 0)
        return 0
    if led.get("ol") is not None:
        return int(led.get("ol") or 0)
    return int(led.get("loss") or 0) if led.get("via") == "split" else 0


def _ofl(led):
    """A day the one-level split read (sv 1, "split") that GA4 flagged with no "(other)" row to measure it by: its
    country in-list part may have hidden "(other)" — worth a read again, by how much unknown."""
    return int(isinstance(led, dict) and int(led.get("sv") or 1) < SPLIT_V and led.get("via") == "split"
               and bool(led.get("fl")))


def _week_loss(mo):
    """A month → {W (the week's Monday): its folded days' measured loss micros}."""
    out = {}
    for x, v in ((mo or {}).get("days") or {}).items():
        if isinstance(v, dict) and v.get("loss"):
            W = _mon(_d(x)).isoformat()
            out[W] = out.get(W, 0) + int(v.get("loss") or 0)
    return out


def _month_oloss(mo):
    """A month → (recoverable "(other)" micros, loss micros, revenue micros, flagged one-level split days) over its
    folded days."""
    ol = lo = t = nf = 0
    rep = mo.get("rep") if isinstance(mo.get("rep"), dict) else {}
    rep_at = str(rep["at"]) if rep.get("sv") == SPLIT_V and rep.get("at") else None
    for led in (mo.get("days") or {}).values():
        if isinstance(led, dict):
            ol += _oloss(led, rep_at)
            nf += _ofl(led)
            lo += int(led.get("loss") or 0)
            t += int(led.get("t") or 0)
    return ol, lo, t, nf


class Cube:
    """One app's cube in a run: the head (+ hot days), the month files loaded on first use, the months a fold touched
    (only those are written), counts for the log line. data_dir None: in memory only."""

    def __init__(self, data_dir, app_id, stream_id):
        self.data_dir, self.app_id, self.stream_id = data_dir, app_id, str(stream_id or "")
        h = load_head(data_dir, app_id) if data_dir else None
        if not h or str(h.get("stream_id") or "") != self.stream_id:     # another stream: start over
            h = {"v": V, "stream_id": self.stream_id, "d": {}}
        self.head = h
        self.m, self.touched = {}, set()
        self.bad = set()                # months whose file is on disk but not a month of this stream (read again)
        self.folded = self.split = self.loss = self.flagged = self.reread = 0
        self.deeper = self.capped = self.rep_days = self.repaired = self.hidden = self.futile = 0
        self.pruned = self.dirty = False    # dirty: the head changed with no read (the repair's / q's queue)
        self.rp = None                  # the repair's copy of a month: {"k", "mo", "dirty", "done"}
        self.qm, self.qtouched = {}, set()  # q month files loaded / changed in the run
        self.q_days = self.q_fl = self.q_calls = self.q_err = 0
        self.q_rr = self.q_rok = 0      # stored "fl" days read again in the run / of them "ok" now
        self.q_out = 0                  # "ok" days taken out of the q files with a week read before it settled
        self.wl = {}                    # {YYYY-MM: {W: loss micros}} of month files not loaded (week_loss)
        self.q_halt = False             # q ended for this app this run (an error of a q read: never the app's run)
        self.um, self.utouched = {}, set()  # users: u month files loaded / changed in the run
        self.uh, self.u_dirty = None, False  # … the users' head (loaded on first use) / changed
        self.u_kept = self.u_days = self.u_calls = self.uc_days = self.uc_calls = self.u_err = self.u_oth = 0

    def month(self, k):
        """Month k's file (loaded once). Missing: an empty month. On disk but unreadable (a damaged gzip, a cut copy …),
        not this format or another stream's: an empty month too, but in `bad` — step_app then reads the WHOLE month
        again before anything is folded into it, so the file is never written over with fewer days than it held."""
        if k not in self.m:
            s = None
            if self.data_dir:
                p = month_path(self.data_dir, self.app_id, k)
                if os.path.exists(p) or os.path.exists(p[:-3]):
                    s = gu.load_store(p)
                    if not _month_ok(s, self.stream_id):
                        self.bad.add(k)
                        if not (isinstance(s, dict) and str(s.get("stream_id") or "") != self.stream_id):
                            self.reread += 1        # this stream's (or unreadable): counted; another stream's: not
                        s = None
            self.m[k] = s if s is not None else _empty_month(self.stream_id)
        return self.m[k]

    def has(self, D):
        k = D.isoformat()
        return k in self.month(k[:7])["days"]

    def fold(self, D, rec):
        """A FINAL day's record into its month — once (a day already in the ledger: nothing)."""
        k = D.isoformat()
        u = rec.pop("u", None)                      # its users (U_ON): their own file, never the month's
        mo = self.month(k[:7])
        if k in mo["days"]:
            return False
        _merge(mo, k, rec)
        self.touched.add(k[:7])
        self.head.setdefault("d", {}).pop(k, None)
        if Q_CALLS > 0 and q_need(rec):             # its q read: in this run (q_fwd) or first in the history fill
            self.head.setdefault("qh", {}).setdefault("p", []).append(k)
        self.folded += 1
        self.count(rec)
        if u is not None:
            self.u_put(k, u, rec, "fold")
        return True

    # ── u: the users of the same reads (module doc, "Users") ──
    def umonth(self, k):
        """Month k's users file (loaded once; none, unreadable or another stream's: empty)."""
        if k not in self.um:
            s = load_u(self.data_dir, self.app_id, self.stream_id, k) if self.data_dir else None
            self.um[k] = s if s is not None else _empty_u(self.stream_id)
        return self.um[k]

    def uhead(self):
        """The users' head (loaded once; none, unreadable or another stream's: empty)."""
        if self.uh is None:
            s = load_uhead(self.data_dir, self.app_id, self.stream_id) if self.data_dir else None
            self.uh = s if s is not None else _empty_uhead(self.stream_id)
        return self.uh

    def u_put(self, D, u, rec, by):
        """A FINAL read's users of day D (its record's "u", rec: its ledger) → its month's users file "c": by "fold"
        (the walk), "fill" (the country users fill: only a day without them), "rep" (the repair: only a day without
        them — the walk's read stays)."""
        if not U_ON or not isinstance(u, dict):
            return False
        mo = self.umonth(D[:7])
        if by != "fold" and D in mo["c"]:
            return False
        mo["c"][D] = dict(u, at=rec.get("at"), by=by, fl=_ufl(rec))
        self.utouched.add(D[:7])
        self.u_kept += by == "fold"
        self.u_oth += bool(u.get("ou"))
        return True

    def u_q(self, D, got, at):
        """A whole no-country read of FOLDED day D (a settled q read, or the All users fill's) → its users ("q"): kept
        unless an "ok" is there (an "fl" is replaced; nothing of q's own file changes)."""
        if not U_ON or "qu" not in got:
            return False
        mo = self.umonth(D[:7])
        old = mo["q"].get(D)
        if isinstance(old, dict) and old.get("s") == "ok":
            return False
        mo["q"][D] = _uq(got, at)
        self.utouched.add(D[:7])
        return True

    def u_hot_c(self, D, rec):
        """A HOT day's record → itself without its users, which go to the users' head (with the read's "at": the
        build takes them only beside that very read) → rec."""
        u = rec.pop("u", None)
        if U_ON and isinstance(u, dict):
            e = self.uhead()["d"].setdefault(D, {})
            e["c"] = dict(u, at=rec.get("at"), fl=_ufl(rec))
            self.u_dirty = True
        return rec

    def u_hot_q(self, D, got, at):
        """A hot day's whole read (q_fwd, the same run as its cube read: `at` = that read's) → its users, head "d"."""
        if U_ON and "qu" in got:
            self.uhead()["d"].setdefault(D, {})["q"] = _uq(got, at)
            self.u_dirty = True

    def u_prune(self, edge, hs, today):
        """The users' head keeps the hot days only (as the head's "d"): a day final now (≤ edge) or out of hs … today
        goes."""
        if not U_ON:
            return
        d = self.uhead()["d"]
        for k in [k for k in d if k <= edge.isoformat() or not hs.isoformat() <= k <= today.isoformat()]:
            d.pop(k)
            self.u_dirty = True

    def save_u(self):
        """The users' head (after the users' months: save())."""
        if self.data_dir and self.u_dirty and self.uh is not None:
            write_json_gz_stable(uhead_path(self.data_dir, self.app_id), self.uh)
        self.u_dirty = False

    def qmonth(self, k):
        """Month k's q file (loaded once; none, unreadable or another stream's: empty — written over when a day is
        read into it: q is a read of its own, never derived from the month)."""
        if k not in self.qm:
            s = load_q(self.data_dir, self.app_id, self.stream_id, k) if self.data_dir else None
            self.qm[k] = s if s is not None else _empty_q(self.stream_id)
        return self.qm[k]

    def q_has(self, D):
        return D in self.qmonth(D[:7])["days"]

    def q_get(self, ga, D):
        """q_read of day D (YYYY-MM-DD), its calls counted. Raises Stop."""
        c0 = ga.calls
        try:
            got = q_read(ga, _d(D))
        finally:
            self.q_calls += ga.calls - c0
        self.q_days += 1
        self.q_fl += got["qs"] != "ok"
        return got

    def tz(self):
        """The property's time zone (the head's; None before refresh_all first wrote it: UTC)."""
        return self.head.get("time_zone") or None

    def q_put(self, D, got, now_iso, again=False):
        """Day D's q into its month's q file — once (a day already there stays as it was read); again: a stored "fl"
        that is not final (q_due) is REPLACED by this read (an "fl" holds no cell: nothing to take out; an "ok" is
        never replaced) — "rt" + 1 when both it and this read were settled and this one is "fl" too."""
        self.u_q(D, got, now_iso)                   # its users (their own file: whatever q keeps of the read)
        mo = self.qmonth(D[:7])
        old = mo["days"].get(D)
        if old is not None and not (again and q_due(old, D, self.tz()) is not None):
            return False
        for X, js in _qw(got["q"], D).items():
            qx = mo["q"].setdefault(X, {})
            for j, ws in js.items():
                w = qx.setdefault(j, {})
                for W, v in ws.items():
                    w[W] = w.get(W, 0) + v
        rec = mo["days"][D] = {"qs": got["qs"], "qt": got["qt"], "qn": got.get("qn", 0), "qx": got.get("qx"),
                               "qr": got["qr"], "at": now_iso}
        if old is not None:
            self.q_rr += 1
            self.q_rok += got["qs"] == "ok"
            if got["qs"] != "ok" and q_settled(D, old.get("at"), self.tz()):
                rec["rt"] = int(old.get("rt") or 0) + 1
        self.qtouched.add(D[:7])
        if old is not None or got["qs"] != "ok":
            self.q_mark(D, rec)
        return True

    def q_mark(self, D, rec):
        """Day D's stored q record → the head's re-read list "qh" "r" ([[D, when due, its week's loss micros]]): in it
        while it is an "fl" that is not final, out of it otherwise."""
        qh = self.head.setdefault("qh", {})
        r = [e for e in qh.get("r") or [] if isinstance(e, list) and len(e) == 3 and e[0] != D]
        due = q_due(rec, D, self.tz())
        if due is not None:
            r.append([D, due, self.week_loss(D)])
        qh["r"] = r
        self.dirty = True

    def q_drop(self, k, ws):
        """Month k's q of the weeks ws (Mondays) taken out: every cell of those weeks and their "ok" days (a week's
        cells hold no day apart: q_early); their "fl" days stay (they hold no cell) → the days taken out."""
        mo = self.qmonth(k)
        for X in list(mo["q"]):
            js = mo["q"][X]
            for j in list(js):
                for W in ws:
                    js[j].pop(W, None)
                if not js[j]:
                    del js[j]
            if not js:
                del mo["q"][X]
        out = sorted(D for D, rec in mo["days"].items()
                     if isinstance(rec, dict) and rec.get("qs") == "ok" and _mon(_d(D)).isoformat() in ws)
        for D in out:
            del mo["days"][D]
        self.qtouched.add(k)
        self.q_out += len(out)
        self.dirty = True
        return out

    def week_loss(self, D):
        """The cube's measured loss micros of day D's week inside its activity month (the build's week: what a read
        of D whole could take back) — from the month in memory, else its file (read once a run per month, never
        loaded into the run, never flagged "bad": a read only)."""
        k = D[:7]
        mo = self.m.get(k)
        if mo is not None:
            wl = _week_loss(mo)
        else:
            wl = self.wl.get(k)
            if wl is None:
                s = gu.load_store(month_path(self.data_dir, self.app_id, k)) if self.data_dir else None
                wl = self.wl[k] = _week_loss(s if _month_ok(s, self.stream_id) else None)
        return wl.get(_mon(_d(D)).isoformat(), 0)

    def q_left(self):
        """Folded days still without q: the pending ones + the queue's (as it was counted)."""
        qh = self.head.get("qh") or {}
        return len(qh.get("p") or []) + sum(int(e[2] or 0) for e in qh.get("todo") or [] if isinstance(e, list)
                                            and len(e) > 2)

    def q_waits(self, now):
        """(pending days not settled yet — no read before they do —, stored "fl" days to read again)."""
        qh = self.head.get("qh") or {}
        today = _pday(now, self.tz())
        return (sum(1 for D in qh.get("p") or [] if not q_ripe(D, today)),
                sum(1 for e in qh.get("r") or [] if isinstance(e, list) and len(e) == 3))

    def count(self, rec):
        """The log's per-day counts, over every day read final in the run (folded by the walk, or read by the
        repair)."""
        self.split += rec.get("via") == "split"
        self.deeper += bool(rec.get("dp"))          # past the first split (its depth, never its calls)
        self.capped += bool(rec.get("cap"))         # the cap left "(other)" a deeper split could read
        self.hidden += bool(rec.get("hd"))          # "(other)" GA4 hid under an in-list, measured by the day's total
        self.futile += bool(rec.get("fu"))          # a split that named nothing new (filters read no more)
        self.loss += bool(rec.get("loss"))          # measured: revenue GA4 left "(other)" / with no install day
        self.flagged += bool(rec.get("fl"))         # GA4's flag with nothing to measure it by (the page's ≈)

    def rep_path(self, k):
        return os.path.join(app_dir(self.data_dir, self.app_id), k + REP)

    def rep(self, k):
        """Month k's repair copy (loaded once): the file of an earlier run when it is this stream's and of SPLIT_V (its
        days are final reads of this split), else empty."""
        if self.rp is None or self.rp["k"] != k:
            s = gu.load_store(self.rep_path(k)) if self.data_dir else None
            if not (_month_ok(s, self.stream_id) and (s.get("rep") or {}).get("sv") == SPLIT_V):
                s = dict(_empty_month(self.stream_id), rep={"sv": SPLIT_V})
            self.rp = {"k": k, "mo": s, "dirty": False, "done": False}
        return self.rp["mo"]

    def drop_rep(self, k):
        """An older repair's copy of month k: gone (never made the month file)."""
        if self.rp is not None and self.rp["k"] == k:
            self.rp = None
        if self.data_dir:
            try:
                os.remove(self.rep_path(k))
            except OSError:
                pass

    def each_month(self):
        """Every month of the app, oldest first, one at a time (on disk: the touched ones written first)."""
        if not self.data_dir:
            yield from sorted(self.m.items())
            return
        self.save()
        for k, s in months(self.data_dir, self.app_id, self.stream_id):
            yield k, self.m.get(k, s)

    def let_go(self, keep):
        """Every month but `keep` written and let go (the repair holds its month and its copy only)."""
        if self.data_dir:
            self.save()
            for k in [k for k in self.m if k != keep]:
                self.m.pop(k)

    def save(self, before=None):
        """The touched months (before: only those older than that month — written and let go: the walk moved on).
        In memory only (no data_dir): nothing to write, every month kept. Without `before`, the repair's copy after
        the months: written while it is being built (once it became its month, save_head removes it — after the
        head that no longer names it)."""
        if not self.data_dir:
            return
        for k in sorted(self.touched):
            if before and k >= before:
                continue
            write_json_gz_stable(month_path(self.data_dir, self.app_id, k), self.m[k])
            self.touched.discard(k)
        for k in sorted(self.qtouched):             # q files (a read of their own: never ahead of anything)
            write_json_gz_stable(q_path(self.data_dir, self.app_id, k), self.qm[k])
        self.qtouched.clear()
        for k in sorted(self.utouched):             # users' months (their own files; as the months: the walk's
            if before and k >= before:              # left ones written and let go)
                continue
            write_json_gz_stable(u_path(self.data_dir, self.app_id, k), self.um[k])
            self.utouched.discard(k)
        if before:
            for k in [k for k in self.m if k < before and k not in self.touched]:
                self.m.pop(k, None)
            for k in [k for k in self.um if k < before and k not in self.utouched]:
                self.um.pop(k, None)
        elif self.rp is not None and not self.rp["done"] and self.rp["dirty"]:
            write_json_gz_stable(self.rep_path(self.rp["k"]), self.rp["mo"])
            self.rp["dirty"] = False

    def save_head(self):
        """The head (after the months: it never runs ahead of them); then a repair's copy that became its month goes
        (a run killed before that leaves a copy no head names: the next repair of that month starts without it)."""
        if self.data_dir:
            write_json_gz_stable(hot_path(self.data_dir, self.app_id), self.head)
        if self.rp is not None and self.rp["done"]:
            self.drop_rep(self.rp["k"])
        self.save_u()                               # the users' head after it (its own file)


def step_app(ga, cube, today, hs, now):
    """One app's run on its cube → "fetched" or "fresh": the walk, the hot days, their q (q_fwd: the hot days this run
    read, the days folded without q that have settled — the final day of Q_SETTLE − FINAL_LAG days ago), the repair
    (when on). Raises Stop (what was folded / read is kept, the cursor where it stopped; the caller saves the months
    and q files, then the head)."""
    h, now_iso, did = cube.head, gu._now_iso(now), False
    edge = today - timedelta(days=FINAL_LAG)
    d = h.setdefault("d", {})
    for k in [k for k in d if k <= edge.isoformat()]:      # final now: a copy read while it was filling never counts
        d.pop(k)                                            # (a hole until the walk folds it — even when the walk stops
        cube.pruned = True                                  # before it)
    hc = h.get("hcut")
    if hc is not None and not (isinstance(hc, dict) and str(hc.get("D") or "") > edge.isoformat()):
        h.pop("hcut")                                       # a hot day's cut memory goes with it (its final read: the
        cube.pruned = True                                  # walk's own cap and memory)
    cube.u_prune(edge, hs, today)                           # the users' hot days: the same days as "d"
    if not h.get("from") or not h.get("next") or hs < _d(h["from"]):  # first walk, or the history start moved back:
        h["from"], h["next"] = hs.isoformat(), hs.isoformat()         # from it (folded days are skipped, not re-read)
        h.pop("done", None)                                 # … and the build waits for the walk again (columns in one go)
    nxt = max(hs, _d(h["next"]))
    h["next"] = nxt.isoformat()
    while nxt <= edge:
        k = nxt.isoformat()[:7]
        cube.save(before=k)                                 # months the walk left: written and let go (≤ 2 held)
        mo = cube.month(k)
        start = max(hs, nxt.replace(day=1))
        if k in cube.bad and any(D.isoformat() not in mo["days"] for D in _days(start, nxt - timedelta(days=1))):
            nxt = start                                     # its file unreadable / not this stream's: the whole month
            h["next"] = nxt.isoformat()                     # again (never written over with only the days after the
            h.pop("done", None)                             # cursor); the build waits for the walk again
            continue
        if nxt.isoformat() in mo["days"]:                   # folded already (a walk from a moved history start, or a
            while nxt <= edge and nxt.isoformat()[:7] == k and nxt.isoformat() in mo["days"]:   # run whose head was
                nxt += timedelta(days=1)                    # not written after its months): past them, read nothing
            h["next"] = nxt.isoformat()
            continue
        b = min(edge, nxt + timedelta(days=BLOCK - 1))
        x = nxt + timedelta(days=1)
        while x <= b:                                       # never a folded day in a block
            if cube.has(x):
                b = x - timedelta(days=1)
                break
            x += timedelta(days=1)
        for D, rec in read_range(ga, nxt, b, h, now_iso):
            cube.fold(D, rec)
            h["next"] = (D + timedelta(days=1)).isoformat()
            h["walk_at"] = now_iso                          # the walk's last step (the page's "on its way" note)
            did = True
        nxt = b + timedelta(days=1)
    h["done"] = True                                        # the walk reached the final edge
    for k in [k for k in d if not (hs.isoformat() <= k <= today.isoformat())]:
        d.pop(k)
    a = max(hs, edge + timedelta(days=1))
    due = gu._hours_since(h.get("hot_at"), now) >= REFRESH_HOURS or h.get("hot_today") != today.isoformat()
    hot_now = []                                            # the hot days this run read (their q: q_fwd)
    if a <= today and due:
        cyc = h.get("hot_cyc")                              # this round of the hot days: one a Stop cut goes on with
        if not (isinstance(cyc, list) and len(cyc) == 2 and cyc[1] == today.isoformat()):  # the days it has not read
            cyc = h["hot_cyc"] = [now_iso, today.isoformat()]     # (the same property day); else a new round
        todo = [D.isoformat() for D in _days(a, today) if str((d.get(D.isoformat()) or {}).get("at") or "") < cyc[0]]
        for x, y in _runs(todo):
            for D, rec in read_range(ga, x, y, h, now_iso, cap=HOT_CAP, key="hcut", hot=True):
                d[D.isoformat()] = cube.u_hot_c(D.isoformat(), rec)     # replaced (never folded: read while not
                #                                                         final); its users to the users' head
                hot_now.append(D.isoformat())
                did = True
        h["hot_at"], h["hot_today"] = now_iso, today.isoformat()
        h.pop("hot_cyc", None)
    if Q_CALLS > 0:
        did = q_fwd(ga, cube, now, hot_now, today) or did  # q of the hot days this run read, settled folded days
    if REPAIR_CALLS > 0:
        did = repair(ga, cube, now) or did                  # with what the run has left
    return "fetched" if did else "fresh"


def _scan(cube):
    """The repair's queue: every month of the app with recoverable "(other)" loss (or one-level split days GA4 flagged
    with no "(other)" row) → [[YYYY-MM, its measured share of the month's revenue]], the biggest share first, the more
    recent month first on a tie (a month with flagged days only: share 0, after every measured one)."""
    q = []
    for k, mo in cube.each_month():
        ol, _, t, nf = _month_oloss(mo)
        if ol > 0 or nf > 0:
            q.append([k, round(ol / t, 6) if t > 0 else (1.0 if ol else 0.0)])
    q.sort(key=lambda e: e[0], reverse=True)
    q.sort(key=lambda e: -e[1])
    return q


def _runs(days):
    """Sorted YYYY-MM-DD days → (a, b) ranges of consecutive days, ≤ BLOCK days each."""
    out = []
    for k in days:
        D = _d(k)
        if out and D == out[-1][1] + timedelta(days=1) and (D - out[-1][0]).days < BLOCK:
            out[-1][1] = D
        else:
            out.append([D, D])
    return out


def _spc(ga):
    """The app's seconds a GA4 call in this run (ga.clock / ga.t_app, set by refresh_all) — None: not known yet."""
    clk = getattr(ga, "clock", None)
    if clk is None or not ga.calls:
        return None
    return max(0.0, clk() - ga.t_app) / ga.calls


def _room(ga, st, first=DAY_CAP + 1, least=MIN_CAP):
    """The run has calls AND time left for what one more day needs: the calls under the app's cap — st's calls a day
    so far ("c" / "n", rounded up; at least `least`), `first` before its first day (the repair: a day's cap and its
    total) —, the time under the run's budget (ga.t_end) for the most calls a day took ("m"; at least that average)
    at the app's seconds a call (this run's, else st's "s": an earlier run's) — a budget Stop throws a started day's
    calls away, a day not started costs nothing. Unknown (no cap, no clock, nothing measured): yes."""
    n = int(st.get("n") or 0)
    need = max(least, -(-int(st.get("c") or 0) // n)) if n else first
    mx = getattr(ga, "max_calls", None)
    if mx is not None and mx - ga.calls < need:
        return False
    clk = getattr(ga, "clock", None)
    s = _spc(ga) or st.get("s")
    return clk is None or not s or ga.t_end - clk() >= max(need, int(st.get("m") or 0)) * float(s)


def _took(ga, st, calls):
    """One more day of `calls` calls into st's "c" / "n" / "m" (the most), and the app's seconds a call so far into
    its "s"."""
    st["c"], st["n"] = int(st.get("c") or 0) + calls, int(st.get("n") or 0) + 1
    st["m"] = max(int(st.get("m") or 0), calls)
    s = _spc(ga)
    if s:
        st["s"] = round(s, 2)


REP_FIELDS = ("k", "old", "at", "c", "n", "m", "cut")


def repair(ga, cube, now):
    """The repair of months folded before the deeper split (module doc) → True when a day was read. Raises Stop (the
    days read kept in the copy; the app's own call cap only ends the repair for this run)."""
    h, now_iso = cube.head, gu._now_iso(now)
    rp = h.get("rep")
    if not isinstance(rp, dict) or rp.get("sv") != SPLIT_V:     # first time, or a newer split: its own queue
        if isinstance(rp, dict) and rp.get("k"):
            cube.drop_rep(rp["k"])
        rp = h["rep"] = {"sv": SPLIT_V}
        cube.dirty = True
    if not rp.get("k"):
        if not rp.get("q") and gu._hours_since(rp.get("scan"), now) >= RESCAN_DAYS * 24:
            rp["q"], rp["scan"] = _scan(cube), now_iso
            cube.dirty = True
        while rp.get("q") and not rp.get("k"):
            k = str(rp["q"].pop(0)[0])
            cube.dirty = True
            ol, lo, t, nf = _month_oloss(cube.month(k))
            if (ol > 0 or nf > 0) and k not in cube.bad:
                cube.drop_rep(k)                            # a copy no head names (a run killed after its month was
                rp.update(k=k, old={"ol": ol, "loss": lo, "t": t}, at=now_iso, c=0, n=0)   # written): never used
            elif cube.data_dir and k not in cube.touched:   # nothing to repair in it (any more): let go
                cube.m.pop(k, None)
    k = rp.get("k")
    if not k:
        return False
    cube.let_go(keep=k)
    live = cube.month(k)
    acc = None if k in cube.bad else cube.rep(k)
    if acc is None or not live["days"] or not acc["days"] and not any(_month_oloss(live)[i] for i in (0, 3)):
        cube.drop_rep(k)                                    # its file unreadable now (never a copy made the month with
        for f in REP_FIELDS:                                # nothing to hold it against), gone (no day to read), or
            rp.pop(f, None)                                 # nothing left to read in it (a run that wrote the repaired
        cube.dirty = True                                   # month but not its head): the next month of the queue next
        return False                                        # run
    did, c0 = False, ga.calls
    try:
        for D in sorted(D for D in live["days"] if D not in acc["days"]):   # day by day: a block of a month with
            if ga.calls - c0 >= REPAIR_CALLS or not _room(ga, rp):         # "(other)" only comes back with it again
                break
            last = ga.calls
            rec = _read_day(ga, _d(D), now_iso, rp, DAY_CAP)
            cube.u_put(D, rec.pop("u", None), rec, "rep")  # its users: only a day without them (never the month's)
            _merge(acc, D, rec)
            cube.rp["dirty"] = did = True
            cube.rep_days += 1
            cube.count(rec)
            _took(ga, rp, ga.calls - last)
    except Stop as e:
        if str(e) != "calls":                               # the budget, the property's quota: the app stops here
            raise
    if live["days"] and all(D in acc["days"] for D in live["days"]):    # every day read again: the copy is the month
        t = _month_oloss(acc)[2]
        nol = sum(int(v.get("ol") or 0) for v in acc["days"].values() if isinstance(v, dict))
        old = rp.get("old") or {}
        acc["rep"] = {"sv": SPLIT_V, "at": now_iso, "ol0": old.get("ol"), "loss0": old.get("loss"), "t0": old.get("t")}
        cube.m[k] = acc
        cube.touched.add(k)
        cube.rp["done"] = True
        cube.repaired += 1
        cube.dirty = True                                   # the head written (k cleared) even in a run with no call
        rp["log"] = (list(rp.get("log") or []) + [[k, old.get("ol"), nol, t, now_iso]])[-LOG_KEEP:]
        for f in REP_FIELDS:
            rp.pop(f, None)
    return did


# ── q: the reads (module doc) ───────────────────────────────────────────────────────────────────────────────────────
def q_fwd(ga, cube, now, hot_now, today=None):
    """q in step_app: the hot days this run read (`hot_now`: their q now, the same moment as their cube read — a hot
    copy of an earlier round never gets one; a hot day of nothing needs none; an "fl" there blocks nothing: the hot
    copy goes at the fold, the folded day waits in "p" for its settled read), then up to Q_FWD days of "p" (folded
    without q, oldest first) that have SETTLED (q_ripe by the property's `today`; a newer one stays in "p" for a later
    run or the fill) → True when a day was read. The app's call cap ends it (the rest stays in "p"); a budget / quota
    Stop goes on up (what was read is kept); any other error ends q for this app this run (counted in q_err, the day it
    was on stays unread) — q is optional: never the app's run."""
    h, now_iso, n0 = cube.head, gu._now_iso(now), cube.q_days
    d = h.get("d") or {}
    today = today or _pday(now, cube.tz())
    try:
        for k in hot_now:
            rec = d.get(k)
            if isinstance(rec, dict) and "qs" not in rec and q_need(rec):
                got = cube.q_get(ga, k)
                rec.update(q=_qw(got["q"], k), qt=got["qt"], qn=got.get("qn", 0), qx=got.get("qx"), qs=got["qs"],
                           qr=got["qr"])
                cube.u_hot_q(k, got, rec.get("at"))         # its users beside that cube read (the users' head)
        _q_p(ga, cube, now_iso, today, lambda: True, Q_FWD)
    except Stop as e:
        if str(e) != "calls":
            raise
    except Exception:
        cube.q_err += 1
        cube.q_halt = True
    return cube.q_days > n0


def q_scan(cube, now):
    """The history fill's queue (head "qh" "todo"), from the month files (no GA4 call): every month with folded days
    that have no q yet → [YYYY-MM, its measured "(other)" share, days without q, loss micros] — the months with loss
    first (the biggest share first, the newer month on a tie), then every other month, newest first. Made when there
    is none and again every RESCAN_DAYS while it is empty (a day folded and never put in "p": a run killed between its
    months and its head — one that has not SETTLED yet goes to "p" instead: read once it has, never before) → True
    when made."""
    qh = cube.head.setdefault("qh", {})
    if qh.get("todo") or gu._hours_since(qh.get("scan"), now) < RESCAN_DAYS * 24:
        return False
    todo, pend, wait, today = [], set(qh.get("p") or []), [], _pday(now, cube.tz())
    for k, mo in cube.each_month():
        qd = cube.qmonth(k)["days"]
        days = {D: v for D, v in (mo.get("days") or {}).items() if isinstance(v, dict)}
        miss, w = _q_miss(days, qd, pend, today)            # (the pending ones: read first, counted there; a day of
        wait += w                                           # nothing: never read)
        if cube.data_dir and k not in cube.qtouched:
            cube.qm.pop(k, None)                            # one month at a time
        if miss:
            lo = sum(int(v.get("loss") or 0) for v in days.values())
            t = sum(int(v.get("t") or 0) for v in days.values())
            todo.append([k, round(lo / t, 6) if t > 0 else (1.0 if lo else 0.0), len(miss), lo])
    todo.sort(key=lambda e: e[0], reverse=True)
    todo.sort(key=lambda e: (e[3] <= 0, -e[1] if e[3] > 0 else 0))
    qh["todo"], qh["scan"] = todo, gu._now_iso(now)
    _q_pend(cube, wait)
    cube.dirty = True
    return True


def _q_miss(days, qd, pend, today):
    """A month's folded days ({D: ledger}) that need a q read and have none (q days qd), not in "p" (pend: read from
    there) → (those that have SETTLED by the property's `today`, oldest first — the queue's; those not settled yet:
    "p"'s, never read before they have)."""
    miss, wait = [], []
    for D, v in sorted(days.items()):
        if q_need(v) and D not in qd and D not in pend:
            (miss if q_ripe(D, today) else wait).append(D)
    return miss, wait


def _q_pend(cube, days):
    """Days folded without a q (or whose q was taken out: q_early) → "p", each once, in date order among the days
    there (_q_p reads each once it has settled)."""
    p = cube.head.setdefault("qh", {}).setdefault("p", [])
    for D in sorted(set(days) - set(p)):
        p.insert(next((i for i, x in enumerate(p) if str(x) > D), len(p)), D)
        cube.dirty = True


def q_rescan(cube, now):
    """The re-read list (head "qh" "r"), from the q files (no GA4 call): every stored "fl" day that is not final
    (q_due: read before it settled, or settled and read again fewer than Q_RETRY times) → [D, when due, its week's
    loss]. Every q_put keeps the list as it goes; this makes it from the files when there is none (q files of an
    older copy of this code: their "fl" days of reads made before the day settled) and again every RESCAN_DAYS (a run
    killed between its q files and its head) → True when made. An "ok" read before its day settled (q_early: q files
    of an older copy of this code) takes its week out of the q file here (Cube.q_drop: the week's cells and "ok" days,
    counted in q_out), those days back in "p" — read again, once settled, like any day folded without q."""
    qh = cube.head.setdefault("qh", {})
    if gu._hours_since(qh.get("rs"), now) < RESCAN_DAYS * 24:
        return False
    keys = set(cube.qm)
    if cube.data_dir:
        try:
            keys.update(f[:7] for f in os.listdir(app_dir(cube.data_dir, cube.app_id))
                        if len(f) == 7 + len(QSUF) and f.endswith(QSUF) and f[4] == "-" and f[:4].isdigit())
        except OSError:
            pass
    r, tz, back = [], cube.tz(), []
    for k in sorted(keys):
        held = k in cube.qm
        qd = cube.qmonth(k)["days"]
        ws = {_mon(_d(D)).isoformat() for D, rec in qd.items() if q_early(rec, D, tz)}
        if ws:                                              # an "ok" read before its day settled: its week out
            back += cube.q_drop(k, ws)
        for D, rec in sorted(qd.items()):
            due = q_due(rec, D, tz)
            if due is not None:
                r.append([D, due, cube.week_loss(D)])
        if cube.data_dir and not held and k not in cube.qtouched:
            cube.qm.pop(k, None)                            # one q file at a time
    qh["r"], qh["rs"] = r, gu._now_iso(now)
    _q_pend(cube, back)
    cube.dirty = True
    return True


class _Out(Exception):
    """The run's q calls (take()) are used up: the fill ends here."""


def _q_again(ga, cube, now_iso, take, lossy):
    """The re-reads due now (head "qh" "r"): those on a week with measured loss (lossy: the biggest loss first — a
    whole read there takes it back) or the others (oldest first). An entry no longer due (final, gone, or due later)
    is set right without a call. Raises _Out (no call left), Stop."""
    tz = cube.tz()
    due = sorted((e for e in (cube.head.get("qh") or {}).get("r") or []
                  if isinstance(e, list) and len(e) == 3 and str(e[1]) <= now_iso and (int(e[2] or 0) > 0) == lossy),
                 key=lambda e: (-int(e[2] or 0), str(e[0])))
    for D, _, _ in due:
        old = cube.qmonth(D[:7])["days"].get(D)
        when = q_due(old, D, tz)
        if when is None or when > now_iso:
            cube.q_mark(D, old)
            continue
        if not take():
            raise _Out
        cube.q_put(D, cube.q_get(ga, D), now_iso, again=True)


def _q_p(ga, cube, now_iso, today, take, most=None):
    """The days of "p" (folded without q, oldest first) that have SETTLED by the property's `today`, read (at most
    `most`); a day not settled yet stays in "p", in its order; a day that has its q already leaves it unread → reads
    made. Raises _Out (take() gave no call), Stop — "p" is right either way (a day whose read did not finish stays)."""
    p = (cube.head.get("qh") or {}).get("p")
    if not p:
        return 0
    i, n, keep = 0, 0, []
    try:
        while i < len(p) and (most is None or n < most):
            D = p[i]
            if not cube.q_has(D):
                if not q_ripe(D, today):                    # not settled yet: its read would not be final
                    keep.append(D)
                    i += 1
                    continue
                if not take():
                    raise _Out
                cube.q_put(D, cube.q_get(ga, D), now_iso)
                n += 1
            i += 1
    finally:
        p[:] = keep + p[i:]
    return n


def q_fill(ga, cube, now, take):
    """The history fill of one app (refresh_all's second round): the stored "fl" days due a read again on weeks with
    measured loss first (the biggest loss first: they take back the most), then "p" (days folded without q — only
    those that have SETTLED: q_ripe; a newer one stays), then the other re-reads due, then the queue's months, each
    month's days without q oldest first — while take() gives a call (the run's Q_CALLS over every app), under the
    app's call cap and the run's budget → days read. Never raises (a Stop ends it: every q day read is kept, the rest
    next run; any other error too, counted in q_err)."""
    qh, now_iso, n0 = cube.head.setdefault("qh", {}), gu._now_iso(now), cube.q_days
    if cube.q_halt:
        return 0
    today = _pday(now, cube.tz())
    try:
        _q_again(ga, cube, now_iso, take, True)
        _q_p(ga, cube, now_iso, today, take)
        _q_again(ga, cube, now_iso, take, False)
        todo = qh.get("todo") or []
        while todo:
            k = str(todo[0][0])
            mo = cube.month(k)                              # its ledger (a month the walk re-reads: in "p" then)
            qd = cube.qmonth(k)["days"]
            miss, wait = ([], []) if k in cube.bad else _q_miss(mo["days"], qd, set(qh.get("p") or []), today)
            _q_pend(cube, wait)                             # "p"'s days (read there once settled) and a day not
            for i, D in enumerate(miss):                    # settled yet (to "p"): never read here
                todo[0][2] = len(miss) - i
                if not take():
                    raise _Out
                cube.q_put(D, cube.q_get(ga, D), now_iso)
            todo.pop(0)
            cube.dirty = True
            if cube.data_dir:                               # the month done: its q written, both let go
                cube.save()
                if k not in cube.touched:
                    cube.m.pop(k, None)
                cube.qm.pop(k, None)
                cube.um.pop(k, None)                        # (its users too: written by save)
    except (_Out, Stop):
        pass
    except Exception:
        cube.q_err += 1
        cube.q_halt = True
    return cube.q_days - n0


def _q_rank(cube, now_iso=None):
    """The fill's order of the apps: those with re-reads due (now_iso; None: every one) on weeks with measured loss
    first (a whole read there takes it back), then those with days of "p" that have SETTLED (by the property's day
    then; None: every day of "p" — a day not settled yet is no work: every app has some), then the most measured loss
    a read could take back (the queue's months without q + the lossy weeks due a re-read, each week once — a week's
    "fl" days carry its loss each), then the most days left."""
    qh = cube.head.get("qh") or {}
    lo = sum(int(e[3] or 0) for e in qh.get("todo") or [] if isinstance(e, list) and len(e) > 3)
    rl = sum({(str(e[0])[:7], _mon(_d(e[0])).isoformat()): int(e[2] or 0) for e in qh.get("r") or []
              if isinstance(e, list) and len(e) == 3 and (now_iso is None or str(e[1]) <= now_iso)}.values())
    today = _pday(now_iso, cube.tz()) if now_iso is not None else None
    ready = any(today is None or q_ripe(D, today) for D in qh.get("p") or [])
    return (not rl, not ready, -(lo + rl), -cube.q_left(), cube.app_id)


# ── u: the two users fills (module doc, "Users") ────────────────────────────────────────────────────────────────────
def _hs(cube):
    """The app's history start (the head's, written by refresh_all; None: not known yet — no users fill)."""
    try:
        return _d(cube.head.get("hs") or cube.head.get("from"))
    except (TypeError, ValueError):
        return None


def _uq_miss(cube, k, mo, hs, today):
    """Month k's folded days (mo: its file) the All users fill reads, newest first: ≥ hs + U_FROM (before it every
    30-day column's age is one the install-day file holds), with a row (a day with none has no user), SETTLED (q's
    rule: a read before is not final), no whole read's users kept yet — and not a day q itself still reads (q on, the
    day needs one, no final q record: that read keeps its users)."""
    if k in cube.bad:
        return []
    qd = cube.qmonth(k)["days"] if Q_CALLS > 0 else {}
    ud, tz, out = cube.umonth(k)["q"], cube.tz(), []
    for D, led in (mo.get("days") or {}).items():
        if not isinstance(led, dict) or D in ud or not int(led.get("rows") or 0):
            continue
        if (_d(D) - hs).days < U_FROM or not q_ripe(D, today):
            continue
        if Q_CALLS > 0 and q_need(led) and not (D in qd and q_final(qd[D], D, tz)):
            continue
        out.append(D)
    return sorted(out, reverse=True)


def _uc_miss(cube, k, mo, hs):
    """Month k's folded days the country users fill reads, newest first: after hs (day hs holds age 0 only: the
    installs, the cube's own "e"), with a row, no users of a final read kept yet."""
    if k in cube.bad:
        return []
    ud, h0 = cube.umonth(k)["c"], hs.isoformat()
    return sorted((D for D, led in (mo.get("days") or {}).items()
                   if isinstance(led, dict) and D > h0 and D not in ud and int(led.get("rows") or 0)), reverse=True)


def _u_let_go(cube, k):
    """Month k done by a users fill: the users' files written, its month / q / users files let go."""
    if cube.data_dir:
        cube.save()
        if k not in cube.touched:
            cube.m.pop(k, None)
        cube.qm.pop(k, None)
        cube.um.pop(k, None)


def u_scan(cube, now, kind):
    """A users fill's queue (users' head kind "qs" — All users — or "cs" — country users —: {"todo": [[YYYY-MM, days to
    read]], "scan"}) from the files (no GA4 call): every month with days to read, newest first. Made when there is none
    and again every RESCAN_DAYS while it is empty (days folded since that the reads did not keep, a run killed between
    its months and its users' files) → True when made."""
    hs = _hs(cube)
    st = cube.uhead().setdefault(kind, {})
    if hs is None or st.get("todo") or gu._hours_since(st.get("scan"), now) < RESCAN_DAYS * 24:
        return False
    today, todo = _pday(now, cube.tz()), []
    for k, mo in cube.each_month():
        miss = _uq_miss(cube, k, mo, hs, today) if kind == "qs" else _uc_miss(cube, k, mo, hs)
        if miss:
            todo.append([k, len(miss)])
        if cube.data_dir:
            if k not in cube.qtouched:
                cube.qm.pop(k, None)                    # one month at a time
            if k not in cube.utouched:
                cube.um.pop(k, None)
    st["todo"], st["scan"] = sorted(todo, reverse=True), gu._now_iso(now)
    cube.u_dirty = True
    return True


def u_fill_q(ga, cube, now, take):
    """The All users fill of one app: its queue's months newest first, each month's days newest first — one whole
    no-country read a day (q_read: every install day's users that day, ~1 token), only its users kept (Cube.u_q: q's
    own file never touched) — while take() gives a call → days read. Raises _Out (no call left), Stop (the run's
    budget, the quota, the app's call cap): every day read is kept, the rest next run."""
    st = cube.uhead().setdefault("qs", {})
    todo, hs, n0 = st.get("todo") or [], _hs(cube), cube.u_days
    now_iso, today = gu._now_iso(now), _pday(now, cube.tz())
    while todo and hs is not None:
        k = str(todo[0][0])
        miss = _uq_miss(cube, k, cube.month(k), hs, today)      # from the files now (a day q read meanwhile: out)
        for i, D in enumerate(miss):
            todo[0][1] = len(miss) - i
            cube.u_dirty = True
            if not take():
                raise _Out
            c0 = ga.calls
            try:
                got = q_read(ga, _d(D))
            finally:
                cube.u_calls += ga.calls - c0
            cube.u_days += 1
            cube.u_q(D, got, now_iso)
        todo.pop(0)
        cube.u_dirty = True
        _u_let_go(cube, k)
    return cube.u_days - n0


class _Meter:
    """An app's GA4 whose every call is taken from a fill's own allowance first (take() False → Stop("u") before the
    call: nothing of a day it cut is kept, as with any Stop); everything else is the app's (its calls, flags, cap)."""

    def __init__(self, ga, take):
        self._ga, self._take = ga, take

    def report_all(self, *a, **k):
        if not self._take():
            raise Stop("u")
        return self._ga.report_all(*a, **k)

    def __getattr__(self, name):
        return getattr(self._ga, name)


def u_fill_c(ga, cube, now, take, left):
    """The country users fill of one app: its queue's months newest first, each month's days to read in runs of
    consecutive days (≤ BLOCK) newest first, each run read again as the cube reads (read_range: a block of the run;
    "(other)", GA4's flags or a cut answer → each day alone and its split under UC_CAP; no day total: users have none —
    what stays "(other)" is the day's "ou", a hidden one its "fl"), only the users kept (Cube.u_put "fill": a day
    without them; the cube's files never touched). A block that had to go day by day: the next HEAVY_KEEP days read
    alone straight away (head "cs" "hk"), then a block is tried again. A run starts only while the allowance holds a
    day's calls (left() ≥ UC_CAP) → days read. Raises _Out, Stop (the days read kept)."""
    st = cube.uhead().setdefault("cs", {})
    todo, hs, n0 = st.get("todo") or [], _hs(cube), cube.uc_days
    now_iso, meter = gu._now_iso(now), _Meter(ga, take)
    while todo and hs is not None:
        k = str(todo[0][0])
        miss = _uc_miss(cube, k, cube.month(k), hs)
        rest = len(miss)
        for a, b in reversed(_runs(sorted(miss))):
            todo[0][1] = rest
            cube.u_dirty = True
            if left() < UC_CAP:
                raise _Out
            mem, n = {}, (b - a).days + 1
            skip = int(st.get("hk") or 0) > 0
            if skip:                                        # read_range's heavy memory: these days alone
                mem["heavy"] = {"at": a.isoformat(), "n": 1}
            c0, r0 = ga.calls, rest
            try:
                for D, rec in read_range(meter, a, b, mem, now_iso, cap=UC_CAP, hot=True):
                    cube.u_put(D.isoformat(), rec.pop("u", None), rec, "fill")
                    cube.uc_days += 1
                    rest -= 1
            finally:                                        # (a Stop too: what the run learnt is kept)
                cube.uc_calls += ga.calls - c0
                if skip:
                    st["hk"] = max(0, int(st["hk"]) - (r0 - rest))
                elif n > 1 and mem.get("heavy"):            # the block came back with "(other)" / flagged / cut
                    st["hk"] = HEAVY_KEEP
        todo.pop(0)
        cube.u_dirty = True
        _u_let_go(cube, k)
    return cube.uc_days - n0


def _u_fills():
    """A users fill is on (U_ON and its calls a run > 0): the apps go to refresh_all's second round."""
    return U_ON and (U_CALLS > 0 or UC_CALLS > 0)


def u_round(fill, now, over, lock, counts, kind, workers=WORKERS):
    """refresh_all's users rounds, after q's: kind "qs" — the All users fill, U_CALLS calls — or "cs" — the country
    users fill, UC_CALLS calls — over every app: each app's queue made where due (u_scan: the files, no GA4 call), then
    its fill, the app whose fill read longest ago first (state "ut" / "uct"; then by id), WORKERS side by side, while
    over() (the run's budget and the round's seconds) lets it; each app's users' files written (never a revenue file).
    Never raises (an error counted in the app's u_err)."""
    left = [U_CALLS if kind == "qs" else UC_CALLS]
    turn = "ut" if kind == "qs" else "uct"

    def take():
        with lock:
            if left[0] <= 0 or over():
                return False
            left[0] -= 1
            return True

    def scan(t):
        try:
            if not over():
                u_scan(t[2], now, kind)
        except Exception:
            t[2].u_err += 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(scan, fill))
    order = sorted(fill, key=lambda t: (t[1].get(turn) or "", t[0]))

    def one(t):
        aid, st, cube, ga = t
        c0, k0, d0 = ga.calls, ga.tok, cube.u_days + cube.uc_days
        cap0 = getattr(ga, "max_calls", None)
        if Q_APP_CALLS > 0 and isinstance(cap0, int):
            ga.max_calls = max(cap0, ga.calls + Q_APP_CALLS)     # the fills' own calls an app a run (as q's)
        try:
            if not over() and left[0] > 0:
                if kind == "qs":
                    u_fill_q(ga, cube, now, take)
                else:
                    u_fill_c(ga, cube, now, take, lambda: left[0])
        except (_Out, Stop):
            pass
        except Exception:
            cube.u_err += 1
        finally:
            if isinstance(cap0, int):
                ga.max_calls = cap0
        try:                                            # the users' months, then the users' head (its queue)
            cube.save()
            cube.save_u()
        except Exception:
            cube.u_err += 1
        with lock:
            if cube.u_days + cube.uc_days > d0:
                st[turn] = gu._now_iso(now)
            counts["calls"] += ga.calls - c0
            counts["tokens"] += ga.tok - k0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, order))


# ── state and the run ───────────────────────────────────────────────────────────────────────────────────────────────
def load_state(data_dir):
    try:
        with open(os.path.join(data_dir, DIR, "state.json"), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and isinstance(raw.get("fetch"), dict):
            return raw
    except (OSError, ValueError):
        pass
    return {"v": 1, "fetch": {}}


def save_state(data_dir, state):
    path = os.path.join(data_dir, DIR, "state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=1)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


COUNTS = ("selected", "with_ga4", "fetched", "fresh", "failed", "deferred", "waiting", "days", "split", "deeper",
          "capped", "hidden", "futile", "loss", "flagged", "reread", "repair_days", "repaired", "q_days", "q_flagged",
          "q_calls", "q_left", "q_unscanned", "q_errors", "q_settling", "q_reread", "q_recovered", "q_fl_wait",
          "q_early", "calls", "tokens")
U_COUNTS = ("u_kept", "u_days", "u_calls", "u_left", "uc_days", "uc_calls", "uc_left", "u_unscanned", "u_other",
            "u_errors")
# U_COUNTS (the log line's last part, only with U_ON): "u_kept" days whose users the walk's own reads kept (no call
# of their own), "u_days" / "u_calls" the All users fill's days read / calls, "u_left" its days still to read (apps
# whose queue is made), "uc_days" / "uc_calls" / "uc_left" the same of the country users fill, "u_unscanned" apps
# with a fill whose queue is not made yet (their days left unknown, never counted as 0), "u_other" days kept with
# users GA4 left "(other)" (measured, never spread), "u_errors" a fill (or its files) that ended on an error other
# than a Stop
# "days" = the days the walk folded; "split" … "flagged" = over every day read final (folded + "repair_days"); "q_days"
# the q days read (hot ones too), "q_flagged" those "fl", "q_left" folded days still without q of the apps whose queue
# is made ("q_unscanned": the apps whose queue is not made yet — their days left unknown, never counted as 0),
# "q_errors" q reads (or an app's fill) that ended on an error other than a Stop (q ended for that app this run);
# "q_settling" days folded without q that have not settled yet (Q_SETTLE: no read before), "q_reread" stored "fl" days
# read again in the run, "q_recovered" those that came back "ok", "q_fl_wait" stored "fl" days still to be read again
# (not final: q_due) after the run, "q_early" "ok" days taken out of the q files in the run with their week (an "ok"
# read before its day settled there: q_early — back in "p", read again once settled)


def q_round(fill, now, over, lock, counts, workers=WORKERS):
    """refresh_all's second round, after every app's walk and hot days (never a property's reads later): each app's q
    queue made where due (q_scan: the month files, no GA4 call), then the history fill (q_fill), the apps in _q_rank's
    order (WORKERS side by side), at most Q_CALLS calls over all of them while over() (the run's budget and Q_SEC) lets
    it; each app's q files and head written. Never raises (an error counted in the app's q_err)."""
    left = [Q_CALLS]

    def take():
        with lock:
            if left[0] <= 0 or over():
                return False
            left[0] -= 1
            return True

    def scan(t):
        try:
            if not over():
                q_rescan(t[2], now)
                q_scan(t[2], now)
        except Exception:
            t[2].q_err += 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(scan, fill))
    now_iso = gu._now_iso(now)
    fill.sort(key=lambda t: _q_rank(t[2], now_iso))

    def one(t):
        aid, st, cube, ga = t
        c0, k0, d0 = ga.calls, ga.tok, cube.q_days
        cap0 = getattr(ga, "max_calls", None)
        if Q_APP_CALLS > 0 and isinstance(cap0, int):
            ga.max_calls = max(cap0, ga.calls + Q_APP_CALLS)     # the fill's own calls this app this run
        try:
            if not over() and left[0] > 0:
                q_fill(ga, cube, now, take)
        except Exception:
            cube.q_err += 1
        finally:
            if isinstance(cap0, int):
                ga.max_calls = cap0
        try:                                            # the q files first, then the head (its queue)
            cube.save()
            if cube.q_days > d0 or cube.dirty:
                cube.save_head()
        except Exception:
            cube.q_err += 1
        with lock:
            counts["calls"] += ga.calls - c0
            counts["tokens"] += ga.tok - k0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, fill))


def refresh_all(cfg, data_dir, apps, now=None, clock=None, budget=BUDGET_SEC, workers=WORKERS):
    """Every selected app (uninstall_build's list) → {"counts", "apps": {app id: fetched|fresh|failed|deferred|
    waiting}}. Never raises; never prints."""
    clock = clock or time.monotonic
    now = now or datetime.now(timezone.utc)
    t0 = clock()
    counts = dict.fromkeys(COUNTS + U_COUNTS, 0)
    out = {"counts": counts, "apps": {}}
    lock = threading.Lock()
    try:
        state = load_state(data_dir)
        ust = gu.load_state(data_dir)
        routes = ust["routes"].get("by_package") or {}
        tokens, _ = ga4_probe.owner_tokens({"GA4_REFRESH_TOKENS": cfg.get("refresh_tokens") or "",
                                            "GA4_REFRESH_TOKEN": cfg.get("refresh_token") or ""})
        owner_rt, access = dict(tokens), {}
        now_iso = gu._now_iso(now)

        def over():
            return "budget" if clock() - t0 >= budget else None
        by_prop = {}
        for a in apps:
            if a.get("same_as") or not a.get("package"):
                continue
            counts["selected"] += 1
            r = routes.get(a["package"])
            if not r:
                continue
            counts["with_ga4"] += 1
            aid = a["app_id"]
            um = gaud._uni_meta(ust, data_dir, aid, r)
            if not um:
                out["apps"][aid] = "waiting"
                continue
            st = state["fetch"].setdefault(aid, {})
            if st.get("fail") and gu._hours_since(st.get("last_try"), now) < RETRY_HOURS:
                out["apps"][aid] = "failed"
                continue
            owner = r.get("owner")
            if owner not in access:
                try:
                    access[owner] = (ga4.access_token(cfg["client_id"], cfg["client_secret"], owner_rt[owner])
                                     if owner in owner_rt else None)
                except Exception:
                    access[owner] = None
            by_prop.setdefault(r["property_id"], []).append((a, st, r, gu._d(um["history_start"])))
        for xs in by_prop.values():                     # turns: an app whose first read a Stop cut with less than the
            xs.sort(key=lambda t: (not t[1].get("late"), t[1].get("turn") or "",    # run's whole allowance first (its
                                   bool(t[1].get("cut")), t[1].get("last_ok") or "",   # day gets one: _read_day); then
                                   t[0]["app_id"]))     # the app that waited longest; on a tie the one cut off last
                                                        # time (a backfill using the budget) after the others

        def one_prop(pid):
            prop = {"quota": None, "stop": None}
            for a, st, r, hs in by_prop[pid]:
                aid = a["app_id"]
                if over() or prop["stop"]:
                    with lock:
                        st["deferred"] = True
                        out["apps"][aid] = "deferred"
                    continue
                tok = access.get(r.get("owner"))
                if not tok:
                    with lock:
                        st.update(last_try=now_iso, fail="auth")
                        out["apps"][aid] = "failed"
                    continue
                tz = ust["tz"].get(pid) or "UTC"
                today = now.astimezone(ZoneInfo(tz)).date()
                cube = Cube(data_dir, aid, r["stream_id"])
                cube.head["time_zone"] = tz                 # (q's settle rule: the property's day, from the first run)
                ga = gf.App(tok, pid, r["stream_id"], prop, over=over, max_calls=MAX_CALLS)
                ga.clock, ga.t_end, ga.t_app = clock, t0 + budget, clock()    # the time a day needs (_room)
                ga.full = ga.t_end - ga.t_app >= FULL_SHARE * budget          # the run's whole allowance (_read_day)
                try:
                    res = step_app(ga, cube, today, hs, now)
                    upd = dict(last_try=now_iso, fail=None, turn=now_iso, cut=None, late=None)
                    if res == "fetched":
                        upd["last_ok"] = now_iso
                except Stop:
                    res, upd = "deferred", dict(deferred=True, turn=now_iso, cut=True, late=getattr(ga, "late", None))
                except Exception as e:
                    res, upd = "failed", dict(last_try=now_iso, fail=gu._fail_kind(e), turn=now_iso, cut=None,
                                              late=None)
                try:                                    # the months first: the head never runs ahead of them
                    cube.save()
                    cube.head.update(v=V, app_id=aid, package=a["package"], property_id=pid,
                                     stream_id=str(r["stream_id"]), time_zone=tz, hs=hs.isoformat())
                    if ga.calls or cube.folded or cube.pruned or cube.dirty:
                        cube.save_head()
                        cube.dirty = False
                    cube.save_u()                       # the users' head (its own file; after the users' months)
                except Exception as e:
                    res, upd = "failed", dict(last_try=now_iso, fail=gu._fail_kind(e))
                if res in ("fetched", "fresh") and (Q_CALLS > 0 or _u_fills()):
                    cube.m.clear()                      # written: the fill reads what it needs again
                    cube.qm.clear()
                    cube.um.clear()
                    with lock:
                        fill.append((aid, st, cube, ga))
                with lock:
                    if res != "deferred":
                        st.pop("deferred", None)
                    st.update(upd)
                    for f in ("cut", "late"):
                        if not st.get(f):
                            st.pop(f, None)
                    st["key"] = gu.file_key(aid)
                    out["apps"][aid] = res
                    counts["calls"] += ga.calls
                    counts["tokens"] += ga.tok
                    counts["days"] += cube.folded
                    counts["split"] += cube.split
                    counts["deeper"] += cube.deeper
                    counts["capped"] += cube.capped
                    counts["hidden"] += cube.hidden
                    counts["futile"] += cube.futile
                    counts["repair_days"] += cube.rep_days
                    counts["repaired"] += cube.repaired
                    counts["loss"] += cube.loss
                    counts["flagged"] += cube.flagged
                    counts["reread"] += cube.reread
                    ran.append((st, cube))

        fill, ran = [], []
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:   # a property with such an app starts first
            list(ex.map(one_prop, sorted(by_prop, key=lambda p: (not any(t[1].get("late") for t in by_prop[p]), p))))
        if fill and Q_CALLS > 0 and not over():         # q's history fill: what every app's run left of the budget,
            tq = clock()                                # at most Q_SEC of it (a run never much longer for it)

            def qover():
                return over() or ("q" if clock() - tq >= Q_SEC else None)
            q_round(fill, now, qover, lock, counts, workers)
        for kind, n, sec in (("qs", U_CALLS, U_SEC), ("cs", UC_CALLS, UC_SEC)):    # the users fills, after q's: what
            if fill and U_ON and n > 0 and not over():                             # the budget left, each at most its
                tu = clock()                                                       # own seconds

                def uover(tu=tu, sec=sec):
                    return over() or ("u" if clock() - tu >= sec else None)
                u_round(fill, now, uover, lock, counts, kind, workers)
        for st, cube in ran:                            # the users' counts (the log: summed; the state: per app)
            if U_ON:
                counts["u_kept"] += cube.u_kept
                counts["u_days"] += cube.u_days
                counts["u_calls"] += cube.u_calls
                counts["uc_days"] += cube.uc_days
                counts["uc_calls"] += cube.uc_calls
                counts["u_other"] += cube.u_oth
                counts["u_errors"] += cube.u_err
                left, made = {}, True
                for kind, n in (("qs", U_CALLS), ("cs", UC_CALLS)):
                    q_ = cube.uhead().get(kind) or {}
                    if n <= 0:
                        continue
                    if q_.get("scan"):
                        left[kind] = sum(int(e[1] or 0) for e in q_.get("todo") or [] if isinstance(e, list)
                                         and len(e) > 1)
                    else:
                        made = False
                counts["u_left"] += left.get("qs", 0)
                counts["uc_left"] += left.get("cs", 0)
                counts["u_unscanned"] += not made
                st["u"] = {"k": cube.u_kept, "d": cube.u_days, "c": cube.u_calls, "cd": cube.uc_days,
                           "cc": cube.uc_calls, "o": cube.u_oth, "err": cube.u_err, "left": left.get("qs"),
                           "cleft": left.get("cs")}
            else:
                st.pop("u", None)
        for st, cube in ran:                            # q's counts (the log: summed; the private state: per app)
            counts["q_days"] += cube.q_days
            counts["q_flagged"] += cube.q_fl
            counts["q_calls"] += cube.q_calls
            counts["q_errors"] += cube.q_err
            counts["q_reread"] += cube.q_rr
            counts["q_recovered"] += cube.q_rok
            counts["q_early"] += cube.q_out
            if Q_CALLS > 0:
                sw, fw = cube.q_waits(now)
                counts["q_settling"] += sw
                counts["q_fl_wait"] += fw
                made = bool((cube.head.get("qh") or {}).get("scan"))     # its queue made: what is left is known
                if made:
                    counts["q_left"] += cube.q_left()
                else:
                    counts["q_unscanned"] += 1
                st["q"] = {"d": cube.q_days, "c": cube.q_calls, "fl": cube.q_fl, "err": cube.q_err,
                           "left": cube.q_left() if made else None, "set": sw, "rr": cube.q_rr, "rok": cube.q_rok,
                           "rw": fw, "out": cube.q_out}
            else:
                st.pop("q", None)
        save_state(data_dir, state)
    except Exception as e:                              # a bug here must never cost the build
        out["error"] = type(e).__name__
    for v in out["apps"].values():
        if v in counts:
            counts[v] += 1
    return out


def log_line(status):
    """The build log's ONE line for this step — counts only."""
    c = (status or {}).get("counts") or {}
    return ("ga4 cube: apps %d, with GA4 %d, fetched %d, fresh %d, failed %d, deferred %d, waiting %d, days folded %d, "
            "split %d, deeper %d, capped %d, hidden %d, futile %d, loss %d, flagged %d, months read again %d, "
            "repair days %d, months repaired %d, q days %d, q flagged %d, q calls %d, q left %d, q unscanned %d, "
            "q errors %d, q settling %d, q reread %d, q recovered %d, q fl waiting %d, q early %d, calls %d, "
            "tokens %d%s%s"
            % tuple([gaud._int(c.get(k)) for k in COUNTS]
                    + [(", u kept %d, u days %d, u calls %d, u left %d, uc days %d, uc calls %d, uc left %d, "
                        "u unscanned %d, u other %d, u errors %d" % tuple(gaud._int(c.get(k)) for k in U_COUNTS))
                       if U_ON else "",
                       (", error " + status["error"]) if (status or {}).get("error") else ""]))
