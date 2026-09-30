"""Daily App Review — lazy, cached, read-only readers over a BUILT site dir (dashboard.json.gz + the lazy files).

A missing or damaged file is None, never an exception. File names taken from the dashboard (the per-app `file`
fields) are accepted only as plain names inside the site dir."""

import gzip
import json
import os
import re

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


class Site:
    def __init__(self, site_dir, dashboard=None):
        self.dir = site_dir
        # an in-memory dashboard is COPIED through JSON: the builder can never mutate the caller's dict, and it
        # reads exactly what the page reads from dashboard.json.gz
        self._dash = json.loads(json.dumps(dashboard)) if dashboard is not None else None
        self._cache = {}

    def _path(self, name):
        if not isinstance(name, str) or not _SAFE_NAME.match(name) or ".." in name:
            return None
        return os.path.join(self.dir, name)

    def _load(self, name):
        if name in self._cache:
            return self._cache[name]
        val = None
        p = self._path(name)
        if p:
            try:
                if name.endswith(".gz"):
                    with gzip.open(p, "rt", encoding="utf-8") as f:
                        val = json.load(f)
                else:
                    with open(p, encoding="utf-8") as f:
                        val = json.load(f)
            except (OSError, EOFError, ValueError, UnicodeDecodeError):
                val = None
        self._cache[name] = val
        return val

    def dashboard(self):
        if self._dash is None:
            self._dash = self._load("dashboard.json.gz")
        return self._dash

    def gz(self, name):
        return self._load(name)

    def js(self, name, default=None):
        v = self._load(name)
        return default if v is None else v
