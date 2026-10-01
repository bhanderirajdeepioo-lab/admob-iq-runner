CREATE TABLE IF NOT EXISTS rv_meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rv_state (
  day TEXT NOT NULL, app TEXT NOT NULL,
  st  TEXT NOT NULL CHECK (st IN ('ok','kal','flag')),
  snz TEXT NOT NULL DEFAULT '[]',               -- JSON array of feature ids snoozed at the moment of this state
  who TEXT NOT NULL, at TEXT NOT NULL,
  PRIMARY KEY (day, app));
CREATE TABLE IF NOT EXISTS rv_actions (           -- append-only; never UPDATE/DELETE
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, who TEXT NOT NULL,
  act TEXT NOT NULL, day TEXT NOT NULL, app TEXT, feature TEXT, note TEXT, ref INTEGER, extra TEXT);
CREATE INDEX IF NOT EXISTS rv_actions_day ON rv_actions(day, id);
CREATE TABLE IF NOT EXISTS rv_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, app TEXT NOT NULL, app_label TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL, who TEXT NOT NULL, at TEXT NOT NULL, deleted_by TEXT, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS rv_notes_day ON rv_notes(day, app);
CREATE TABLE IF NOT EXISTS rv_flags (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, app TEXT NOT NULL, app_label TEXT NOT NULL DEFAULT '',
  feature TEXT,                                 -- NULL = poori app
  note TEXT NOT NULL DEFAULT '', raised_by TEXT NOT NULL, raised_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','kaam','closed','withdrawn')),
  decision TEXT CHECK (decision IN ('theek','kaam','band')), dec_note TEXT, dec_by TEXT, dec_at TEXT,
  done_note TEXT, done_by TEXT, done_at TEXT, wd_by TEXT, wd_at TEXT,
  dec_day TEXT, done_day TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS rv_flags_one_open ON rv_flags(app, ifnull(feature,'*')) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS rv_flags_status ON rv_flags(status, day);
CREATE INDEX IF NOT EXISTS rv_flags_day ON rv_flags(day);
CREATE TABLE IF NOT EXISTS rv_snoozes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, app_label TEXT NOT NULL DEFAULT '', feature TEXT NOT NULL,
  day TEXT NOT NULL, until TEXT NOT NULL, days INTEGER NOT NULL CHECK (days IN (7,14)), note TEXT NOT NULL DEFAULT '',
  who TEXT NOT NULL, at TEXT NOT NULL, cleared_by TEXT, cleared_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS rv_snoozes_one_live ON rv_snoozes(app, feature) WHERE cleared_at IS NULL;
CREATE TABLE IF NOT EXISTS config_log (            -- append-only: every Settings save through /api/config/save
  id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT NOT NULL, at TEXT NOT NULL, file TEXT NOT NULL,
  bytes INTEGER NOT NULL, result TEXT NOT NULL, commit_sha TEXT);
CREATE TABLE IF NOT EXISTS cmp_marks (            -- 📌 saved dates of "compare any date" (app = an AdMob app id or '*')
  id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, date TEXT NOT NULL, name TEXT NOT NULL,
  who TEXT NOT NULL, at TEXT NOT NULL, deleted_by TEXT, deleted_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS cmp_marks_one_live ON cmp_marks(app, date, name) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS cmp_marks_log (        -- append-only: every add / delete of a saved date
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, who TEXT NOT NULL,
  act TEXT NOT NULL CHECK (act IN ('add','delete')), mark INTEGER NOT NULL,
  app TEXT NOT NULL, date TEXT NOT NULL, name TEXT NOT NULL);
INSERT OR IGNORE INTO rv_meta (k, v) VALUES ('schema_version', '4');
