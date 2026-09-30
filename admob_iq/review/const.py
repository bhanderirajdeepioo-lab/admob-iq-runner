"""Daily App Review — every threshold and fixed word list in one place (no code runs at import)."""

# ── row rules (same numbers as the Aaj page rules) ─────────────────────────────────────────────
NAYA_DAYS = 10               # a change that started ≤ this many days ago is 🆕 Naya
THEEK_SHOW_DAYS = 7
PURANA_DAYS = 30
DROP_DAYS = 90               # rows that started longer ago than this are dropped from the lists
PURANI_HALAT_DAYS = 60       # a level flat for longer than this is "purani halat" (never 🔴)
BADI = 300.0                 # kamai + ads spend ≥ this USD/day: a big app
CHHOTI = 30.0                # below this USD/day: a small app (grouped, never lifted)
RED_REV_REL = 0.20           # app kamai 7 days vs the 7 before: ±20% …
RED_REV_ABS = 20.0           # … and ≥ $20/day
ADUNIT_MIN_LOSS = 10.0       # an ad unit drop worth a row ($/day)
ADUNIT_RED_DAYS = 3

# ── review-only rules ─────────────────────────────────────────────────────────────────────────
KAL_DROP_REL = 0.30          # kal ki kamai vs usual: a sudden 1-day drop worth a look
KAL_DROP_ABS = 20.0
ADS_ROAS_DROP = 0.20
ADS_CPI_UP = 0.30
ADS_ROAS_UP = 0.20
DED_RED_PCT = 0.15
DED_RED_USD = 20.0
DED_AMB_PCT = 0.05
DED_AMB_USD = 5.0
MED_DROP_SHARE = 0.10        # a network that had ≥ 10% of kamai and fell below 1/3 of it
UPDATE_DAYS = 60
EXPAND_TOP = 3
ECPM_MIN_IMPR = 200          # below this many impressions the ad rate is noise

# ── snapshots ─────────────────────────────────────────────────────────────────────────────────
REVIEW_READY_IST_DEFAULT = "09:00"
FAIL_RATIO = 0.5
DOC_V = 1
MAX_MORE = 12                # "Is feature me aur" rows kept per feature

FEATS = [("kamai", "Kamai · eCPM"), ("uninstall", "Uninstall"), ("active", "Active users"),
         ("value", "Install value"), ("update", "Update impact"), ("ads", "Ads"),
         ("deduct", "Deductions"), ("mediation", "Mediation"), ("health", "Account health"),
         ("setup", "Setup / data")]
FEAT_IDS = tuple(f for f, _ in FEATS)
FEAT_LABEL = dict(FEATS)
FEAT_TAB = {"kamai": "Overview / Alerts", "uninstall": "Uninstall", "active": "Active users",
            "value": "Install value", "update": "Uninstall → Updates ka asar", "ads": "Marketing ROAS",
            "deduct": "Deductions", "mediation": "Mediation", "health": "Account health", "setup": "Settings"}
FEAT_PRI = {"deduct": 0, "update": 1, "kamai": 2, "uninstall": 3, "active": 4, "ads": 5, "value": 6, "setup": 7,
            "health": 8, "mediation": 9}

TR = {"red": 4, "amber": 3, "green": 2, "normal": 1, "info": 1, "wait": 0, "na": 0, "nodata": 0}
TIER_RANK = {"red": 4, "amber": 3, "green": 2, "info": 1}
STWORD = {"red": "Bigda", "amber": "Dhyan do", "green": "Behtar", "normal": "Normal", "wait": "Abhi jaldi",
          "na": "Lagu nahi", "nodata": "data nahi"}
WORD = {"red": "Bigda", "amber": "Dhyan do", "green": "Behtar", "info": "Jaankari"}
SRC_TAG = {"uninstall": "Uninstall", "active": "Active users", "value": "Install value", "adunit": "Ad unit",
           "ads": "Ads", "deduct": "Deductions", "health": "Deductions", "mediation": "Mediation",
           "setup": "Setup", "impact": "Update impact"}

# the row kinds added by the review (their 5 answers come from text.q_extra)
EXTRA_KINDS = ("range", "ads", "med", "kal_drop", "setup", "ded", "ah_ivt", "upd")
# head rows that never get a chart of their own (the kamai / ads features fall back to a 14-day chart)
NO_CHART_KINDS = ("range", "ads", "med", "kal_drop", "setup", "pay_never", "act_ads", "n1", "info", "val_info", "upd")

MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WDAY = ("Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar")

UNIT_WORD = (("caller", "Caller-card ad", "call ke baad wali screen ka ad"),
             ("callercad", "Caller-card ad", "call ke baad wali screen ka ad"),
             ("splash", "Splash ad", "app khulte hi aane wala splash ad"),
             ("appopen", "App-open ad", "app khulte hi aane wala ad"),
             ("banner", "Banner", "banner"), ("interstitial", "Full-screen ad", "full-screen ad"),
             ("native", "Native ad", "native ad"))
