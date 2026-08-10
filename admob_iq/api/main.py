"""FastAPI backend — serves engine-computed data (via dataservice.build_dashboard).

The frontend can fetch `/dashboard` once for everything, or hit individual
screen endpoints. In production, dataservice reads the DB; here it computes from
a labeled demo dataset so the whole stack runs with no creds.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .dataservice import build_dashboard, build_from_db

app = FastAPI(title="AdMob IQ", version="0.2.0")

# The dashboard is served behind Cloudflare Access; CORS open here for local/dev.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_CACHE = None


def _data():
    """Use REAL data from Postgres when the fetcher has populated it; else demo."""
    global _CACHE
    if _CACHE is None:
        import os
        url = os.getenv("DATABASE_URL")
        if url:
            try:
                from ..db import PgRepo
                repo = PgRepo(url)
                if repo.has_data():
                    _CACHE = build_from_db(repo)
                    return _CACHE
            except Exception:
                pass
        _CACHE = build_dashboard()
    return _CACHE


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dashboard")
def dashboard():
    """Everything the frontend needs in one call."""
    return _data()


@app.get("/overview")
def overview():
    d = _data()
    return {"kpis": d["kpis"], "revenue_trend": d["placements"][0]["trend"],
            "movers": {"increasing": len(d["movers"]["increasing"]),
                       "decreasing": len(d["movers"]["decreasing"])},
            "alerts": d["alerts"]["counts"]}


@app.get("/apps")
def apps():
    return {"apps": _data()["apps"]}


@app.get("/placements")
def placements():
    return {"placements": _data()["placements"]}


@app.get("/movers")
def movers():
    return _data()["movers"]


@app.get("/alerts")
def alerts():
    return _data()["alerts"]


@app.get("/deductions")
def deductions():
    return _data()["deductions"]


@app.get("/mediation")
def mediation():
    return _data()["mediation"]


@app.get("/recommendations")
def recommendations():
    return _data()["recommendations"]


@app.get("/account-health")
def account_health():
    return _data()["account_health"]
