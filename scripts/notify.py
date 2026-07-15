#!/usr/bin/env python3
"""Email the site owner when an autonomous routine needs intervention. Stdlib only.

  python3 notify.py test
  python3 notify.py send --subject "..." --body "..." [--level alert|info]

Reads SMTP config from the environment, else from ~/.claude/.env:
  SMTP_HOST                 e.g. smtp.gmail.com
  SMTP_PORT                 default 587 (STARTTLS); use 465 for implicit SSL
  SMTP_USER                 SMTP username (usually the full email address)
  SMTP_PASS                 SMTP password / app-password (NEVER hard-coded here)
  NOTIFY_EMAIL_TO           the owner's address — the ONLY recipient
  NOTIFY_EMAIL_FROM         optional; defaults to SMTP_USER

SECURITY: the recipient is ALWAYS `NOTIFY_EMAIL_TO` from config — it is never taken
from a caller/argument. A routine that processes web content therefore cannot redirect
the email to an attacker-supplied address (prompt-injection safe by construction).

Fails soft: if SMTP is not configured, prints a notice and exits 0 so a routine that
calls it is never broken merely because email isn't set up yet. `--strict` → exit 1.
"""
from __future__ import annotations

import argparse
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

REQUIRED = ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "NOTIFY_EMAIL_TO")


class Skip(Exception):
    """Non-fatal: print notice, exit 0 (or 1 with --strict)."""


def load_env() -> dict:
    cfg = {k: os.environ[k] for k in
           ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS",
            "NOTIFY_EMAIL_TO", "NOTIFY_EMAIL_FROM") if os.environ.get(k)}
    env_file = Path.home() / ".claude" / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            line = re.sub(r"^\s*export\s+", "", line.strip())
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k.startswith(("SMTP_", "NOTIFY_EMAIL_")) and k not in cfg:
                cfg[k] = v.strip().strip("'\"")
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        raise Skip(f"email not configured — missing {', '.join(missing)} in ~/.claude/.env")
    cfg.setdefault("SMTP_PORT", "587")
    cfg.setdefault("NOTIFY_EMAIL_FROM", cfg["SMTP_USER"])
    return cfg


def send_email(cfg: dict, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["NOTIFY_EMAIL_FROM"]
    msg["To"] = cfg["NOTIFY_EMAIL_TO"]          # owner only — never a caller argument
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)

    host, port = cfg["SMTP_HOST"], int(cfg["SMTP_PORT"])
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
                s.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise Skip(f"SMTP auth failed ({e.smtp_code}) — check SMTP_USER/SMTP_PASS "
                   f"(Gmail needs an App Password, not your login password)")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise Skip(f"SMTP send failed: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("test", help="send a test email")
    p.add_argument("--strict", action="store_true")
    p = sub.add_parser("send", help="send an alert")
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--level", choices=["alert", "info"], default="alert")
    p.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    try:
        cfg = load_env()
        if args.cmd == "test":
            send_email(cfg, "✅ SEO factory — email alerts are working",
                       "This is a test from notify.py. If you received this, the "
                       "autonomous routines can now email you when intervention is "
                       "needed.\n\n— app-seo-factory")
            print(f"test email sent to {cfg['NOTIFY_EMAIL_TO']}")
        else:
            prefix = "🔴 " if args.level == "alert" else "ℹ️ "
            send_email(cfg, prefix + args.subject, args.body)
            print(f"emailed {cfg['NOTIFY_EMAIL_TO']}: {args.subject}")
        return 0
    except Skip as e:
        print(f"⚠️  NOTIFY SKIPPED: {e}", file=sys.stderr)
        return 1 if getattr(args, "strict", False) else 0


if __name__ == "__main__":
    sys.exit(main())
