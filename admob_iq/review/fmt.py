"""Daily App Review — number, date and money formatting (Hinglish, Roman script only).

Money never becomes HTML here: `money()` returns a sentinel token that `rt()` turns into a rich-text (RT) money
segment {"usd", "s", "sign", "p"} (the page formats it with its ₹/$ toggle) and `plain()` renders as USD text.
Every date is shown relative to the review day (ctx.day): the year is printed only when it differs."""

import re
from datetime import date, timedelta

from .const import MON, UNIT_WORD

_MONEY_RE = re.compile(r"\x00m\|(-?\d+(?:\.\d+)?)\|([^|\x00]*)\|([01])\|([02])\x00")


def D(x):
    """'2026-09-21' / date / None → date / None."""
    if x is None or isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])


def days_back(end, n):
    """The n ISO days ending on `end` (oldest first)."""
    end = D(end)
    return [(end - timedelta(i)).isoformat() for i in range(n - 1, -1, -1)]


def fd(ctx, x):
    x = D(x)
    return f"{x.day} {MON[x.month - 1]}" + (f" {x.year}" if x.year != ctx.day.year else "")


def fr(ctx, a, b):
    a, b = D(a), D(b)
    if a == b:
        return fd(ctx, a)
    if a.year == b.year and a.month == b.month:
        return f"{a.day}–{b.day} {MON[b.month - 1]}" + (f" {b.year}" if b.year != ctx.day.year else "")
    return f"{fd(ctx, a)}–{fd(ctx, b)}"


def age_days(ctx, x):
    return (ctx.day - D(x)).days


def umar(n):
    if n <= 30:
        return f"{n} din"
    if n < 90:
        return f"{round(n / 7)} hafte"
    return f"{round(n / 30)} mahine"


def umar_se(n):
    """'7 din se' / '3 hafte se' — an age of 0 days is 'aaj se', never '0 din se'."""
    return "aaj se" if n <= 0 else f"{umar(n)} se"


def pct(x, plus=True):
    s = f"{x * 100:+.0f}%" if plus else f"{abs(x) * 100:.0f}%"
    return s.replace("-", "−")


def p100(x):
    v = x * 100
    return (f"{v:.1f}".rstrip("0").rstrip(".")) if v < 10 else f"{v:.0f}"


def users(n):
    n = float(n)
    if n >= 1e5:
        return f"{n / 1e5:.1f} lakh"
    return f"{n:,.0f}"


def usd_txt(v):
    a = abs(v)
    s = f"{a:,.0f}" if a >= 10 else f"{a:,.1f}"
    return ("−" if v < 0 else "") + "$" + s


def money(v, din=True, sign=False, p=0):
    """A money token (USD). din → '/din' suffix; sign → '+' for a positive amount; p=2 → small amounts (ad rate,
    cost per install) with 2 decimals under $10."""
    return f"\x00m|{float(v):.4f}|{'/din' if din else ''}|{1 if sign else 0}|{2 if p == 2 else 0}\x00"


def usd2(v):
    return money(v, din=False, p=2)


def money_text(usd, s="", sign=0, p=0):
    """The USD text of one money token — what the page shows in $ mode."""
    if p == 2:
        a = abs(usd)
        t = ("−" if usd < 0 else "") + (f"${a:,.2f}" if a < 10 else f"${a:,.1f}")
    else:
        t = usd_txt(usd)
    if sign and usd > 0:
        t = "+" + t
    return t + (s or "")


def rt(text):
    """A text with money tokens → RT: the plain string when it has no money, else a list of strings and money
    segments {"usd", "s", "sign", "p"}."""
    if text is None:
        return None
    s = str(text)
    if "\x00" not in s:
        return s
    out, pos = [], 0
    for m in _MONEY_RE.finditer(s):
        if m.start() > pos:
            out.append(s[pos:m.start()])
        out.append({"usd": round(float(m.group(1)), 4) + 0.0, "s": m.group(2), "sign": int(m.group(3)),
                    "p": int(m.group(4))})
        pos = m.end()
    if pos < len(s):
        out.append(s[pos:])
    return [x.replace("\x00", "") if isinstance(x, str) else x for x in out if x != ""]


def plain(text):
    """A text with money tokens → plain USD text."""
    if text is None:
        return ""
    if isinstance(text, list):
        return "".join(x if isinstance(x, str) else money_text(x["usd"], x.get("s", ""), x.get("sign", 0),
                                                               x.get("p", 0)) for x in text)
    return _MONEY_RE.sub(lambda m: money_text(float(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))),
                         str(text)).replace("\x00", "")


def ver_of(label):
    """'v1.1.1 → v1.1.2' -> 'v1.1.2'; 'App update' stays."""
    if not label:
        return None
    return label.split("→")[-1].strip()


def rate_txt(v):
    return f"{v * 100:.1f}".rstrip("0").rstrip(".")


def mon_lab(ctx, ym):
    y_, m_ = int(ym[:4]), int(ym[5:7])
    return MON[m_ - 1] + (f" {y_}" if y_ != ctx.day.year else "")


def unit_word(name):
    n = (name or "").lower()
    for k, short, long_ in UNIT_WORD:
        if k in n:
            return short, long_
    return "Ad unit", "ad"
