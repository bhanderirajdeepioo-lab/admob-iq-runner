"""QA for the PER-METRIC approval layer: each metric approved individually (pending/approved/
update), placement rollup incl. 'partial', country per-metric, and old-flat-shape upgrade."""

from admob_iq.db import nest_monthly, nest_daily
from admob_iq.engine.baseline_report import build_baseline
from admob_iq.engine.approvals import apply_approvals, load_approved, _direction, _norm_place, range_alerts


def _cell(unit, country, month, impr, clicks, earn, ec_lo, ec_hi):
    return dict(ad_unit_id=unit, app_id="a", app_name="App", unit_name=unit, country=country,
                month=month, days=30, ad_requests=impr + 2000, matched_requests=impr + 1000,
                impressions=impr, clicks=clicks, estimated_earnings_micros=earn,
                ctr_min=0.008, ctr_max=0.012, match_min=0.9, match_max=0.95,
                show_min=0.9, show_max=0.95, ecpm_min=ec_lo, ecpm_max=ec_hi,
                ctr_avg=clicks / impr, match_avg=0.92, show_avg=0.92, ecpm_avg=earn / 1e6 / impr * 1000)


def _payload():
    cells = []
    for u, ecpm in (("U1", 40_000_000), ("U2", 20_000_000)):     # eCPM 5.0 and 2.5
        for mo in ("2026-04", "2026-05", "2026-06"):
            cells.append(_cell(u, "US", mo, 8000, 80, ecpm, 4.5, 5.5))
    acm = nest_monthly({"units": {}, "data": {}}, cells)
    return build_baseline(acm, nest_daily([]), active_since="2026-01")


def test_pending_when_no_approval():
    p = apply_approvals(_payload(), {"placements": {}})
    for u in p["units"]:
        assert u["appr_status"] == "pending"
        assert u["approved"] == {}                                  # nothing locked
        assert all(v == "pending" for v in u["appr_by_metric"].values())
    assert p["approval_counts"]["pending"] == len(p["units"])
    assert p["approval_metric_counts"]["pending"] == len(p["units"]) * 4


def test_single_metric_approve_is_partial():
    p = _payload()
    u = p["units"][0]
    # approve ONLY ecpm at the range the data itself suggests — the other three stay pending
    sug = u["range"]["ecpm"]
    approved = {"placements": {u["id"]: {"metrics": {"ecpm": {"range": sug, "approved_at": "2026-06"}}}}}
    apply_approvals(p, approved)
    au = next(x for x in p["units"] if x["id"] == u["id"])
    assert au["appr_by_metric"]["ecpm"] == "approved"
    assert au["appr_by_metric"]["ctr"] == "pending"
    assert au["appr_by_metric"]["match"] == "pending"
    assert au["appr_status"] == "partial"                          # mix of approved + pending
    assert au["approved"]["ecpm"] == sug
    assert "ctr" not in au["approved"]
    assert au["status"]["ecpm"] == "in"                            # latest eCPM inside its own range


def test_all_metrics_approved_is_approved():
    p = _payload()
    u = p["units"][0]
    mets = {k: {"range": u["range"][k], "approved_at": "2026-06"} for k in ("ctr", "match", "show", "ecpm")}
    apply_approvals(p, {"placements": {u["id"]: {"metrics": mets}}})
    au = next(x for x in p["units"] if x["id"] == u["id"])
    assert au["appr_status"] == "approved"
    assert all(v == "approved" for v in au["appr_by_metric"].values())


def test_update_flagged_per_metric_when_data_moved_up():
    p = _payload()
    u = p["units"][0]                                              # suggested eCPM ~5.0 (flat months)
    # approved an OLD (earlier-month), lower eCPM range -> a newer month closed -> flips to 'update' up
    approved = {"placements": {u["id"]: {"metrics": {"ecpm": {"range": [2.0, 3.0], "approved_at": "2026-04"}}}}}
    apply_approvals(p, approved)
    au = next(x for x in p["units"] if x["id"] == u["id"])
    assert au["appr_by_metric"]["ecpm"] == "update"
    assert au["appr_dir"]["ecpm"] == "up"
    assert au["appr_status"] == "update"                          # any metric 'update' -> placement 'update'


def test_no_update_same_month_even_if_range_differs():
    # approving in the SAME complete month must NOT immediately flag 'update' (monthly review only)
    p = _payload()
    u = p["units"][0]
    last = p["data_range"]["last"]                                 # newest complete month
    apply_approvals(p, {"placements": {u["id"]: {"metrics": {"ecpm": {"range": [2.0, 3.0], "approved_at": last}}}}})
    au = next(x for x in p["units"] if x["id"] == u["id"])
    assert au["appr_by_metric"]["ecpm"] == "approved"             # suppressed this month, no nag
    # a NEWER complete month having closed (approved earlier) -> now it may flag the update
    p2 = _payload()
    apply_approvals(p2, {"placements": {u["id"]: {"metrics": {"ecpm": {"range": [2.0, 3.0], "approved_at": "2026-03"}}}}})
    au2 = next(x for x in p2["units"] if x["id"] == u["id"])
    assert au2["appr_by_metric"]["ecpm"] == "update"


def test_country_per_metric_applied():
    p = _payload()
    u = p["units"][0]
    us_sug = next(c for c in p["unit_geo"][u["id"]] if c["country"] == "US")["range"]["ecpm"]
    approved = {"placements": {u["id"]: {"metrics": {},
                "countries": {"US": {"metrics": {"ecpm": {"range": us_sug, "approved_at": "2026-06"}}}}}}}
    apply_approvals(p, approved)
    us = next(c for c in p["unit_geo"][u["id"]] if c["country"] == "US")
    assert us["appr_by_metric"]["ecpm"] == "approved"
    assert us["appr_by_metric"]["ctr"] == "pending"
    assert us["approved"]["ecpm"] == us_sug


def test_old_flat_shape_upgraded():
    p = _payload()
    u = p["units"][0]
    # old FLAT shape (pre-per-metric) must upgrade so every metric gets a locked range (not pending)
    old = {"approved_at": "2026-05",
           "range": {k: u["range"][k] for k in ("ctr", "match", "show", "ecpm")},
           "countries": {"US": {"ecpm": [0.0, 100.0]}}}
    apply_approvals(p, {"placements": {u["id"]: old}})
    au = next(x for x in p["units"] if x["id"] == u["id"])
    assert all(v in ("approved", "update") for v in au["appr_by_metric"].values())   # none pending → upgraded
    assert au["approved"]["ecpm"] == u["range"]["ecpm"]
    us = next(c for c in p["unit_geo"][u["id"]] if c["country"] == "US")
    assert us["approved"]["ecpm"] == [0.0, 100.0]                 # old flat country upgraded too


def test_norm_place_mixed_shapes():
    # placement metrics new-shape, one country old-flat, one country new-shape
    norm = _norm_place({"metrics": {"ctr": {"range": [0.01, 0.02]}},
                        "countries": {"US": {"ecpm": [1.0, 2.0]},
                                      "IN": {"metrics": {"ctr": {"range": [0.01, 0.03], "approved_at": "x"}}}}})
    assert norm["metrics"]["ctr"]["range"] == [0.01, 0.02]
    assert norm["countries"]["US"]["metrics"]["ecpm"]["range"] == [1.0, 2.0]
    assert norm["countries"]["IN"]["metrics"]["ctr"]["range"] == [0.01, 0.03]


def test_direction_helper():
    assert _direction([9, 11], [4, 6]) == "up"      # midpoint 10 vs 5
    assert _direction([1, 2], [4, 6]) == "down"     # midpoint 1.5 vs 5
    assert _direction([4.9, 5.1], [4.8, 5.2]) == "same"


def test_load_approved_missing_is_empty(tmp_path):
    assert load_approved(str(tmp_path / "nope.json")) == {"placements": {}}


def test_range_alerts_only_for_approved_out_of_range():
    p = _payload()
    u = p["units"][0]                                # latest eCPM ~5.0
    # approve an eCPM range the latest is clearly BELOW -> should raise a warning alert
    apply_approvals(p, {"placements": {u["id"]: {"metrics": {"ecpm": {"range": [8.0, 9.0]}}}}})
    al = range_alerts(p)
    mine = [a for a in al if a["id"] == u["id"]]
    assert mine and mine[0]["metric"] == "ecpm" and mine[0]["dir"] == "below"
    assert mine[0]["severity"] == "warning"          # eCPM below approved = revenue risk
    # a placement with NO approvals must not appear (pending has no locked standard)
    p2 = apply_approvals(_payload(), {"placements": {}})
    assert range_alerts(p2) == []
