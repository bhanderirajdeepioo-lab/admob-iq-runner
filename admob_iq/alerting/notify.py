"""Free notification channels: Telegram (bot API) + Email (SMTP).

`dry_run=True` (the safe default) formats and returns the message instead of
sending — used by tests and first-run so nothing leaks before creds are set."""

SEVERITY_ICON = {"critical": "🔴", "warning": "🟠", "watch": "🟡", "good": "🎉"}


def format_signal(sig, placement: str = "", country=None) -> str:
    geo = country or "all countries"
    icon = SEVERITY_ICON.get(sig.severity, "•")
    return f"{icon} [{sig.severity.upper()}] {placement} — {sig.message} · {geo}"


def send_telegram(text: str, token: str, chat_id: str, dry_run: bool = True) -> dict:
    if dry_run or not token:
        return {"channel": "telegram", "dry_run": True, "text": text}
    import requests
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": text}, timeout=10)
    return {"channel": "telegram", "status": r.status_code}


def send_email(subject: str, body: str, cfg: dict, dry_run: bool = True) -> dict:
    if dry_run or not cfg.get("host"):
        return {"channel": "email", "dry_run": True, "subject": subject, "body": body}
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = cfg["to"]
    msg.set_content(body)
    with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
        s.starttls()
        s.login(cfg["user"], cfg["pass"])
        s.send_message(msg)
    return {"channel": "email", "status": "sent"}


def notify(signals, cfg: dict) -> list:
    """Route: critical/warning/good -> Telegram immediately; all -> email digest.
    Returns the list of delivery results (or dry-run payloads)."""
    dry = cfg.get("notify_dry_run", True)
    results = []
    lines = []
    for sig, placement, country in signals:
        text = format_signal(sig, placement, country)
        lines.append(text)
        if sig.severity in ("critical", "warning", "good"):
            results.append(send_telegram(text, cfg.get("telegram_token", ""),
                                         cfg.get("telegram_chat", ""), dry))
    if lines:
        results.append(send_email("AdMob IQ — alerts", "\n".join(lines),
                                   cfg.get("smtp", {}), dry))
    return results
