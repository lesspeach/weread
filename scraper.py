"""UNGM Event Tender Monitor

Scrapes https://www.ungm.org/Public/Notice for tenders published in the past
24 hours whose title contains 'event', then sends an email summary.

Required environment variables:
    RECIPIENT_EMAIL  - address(es) to notify, comma-separated
    SENDER_EMAIL     - from address
    SMTP_HOST        - e.g. smtp.gmail.com
    SMTP_PORT        - defaults to 587
    SMTP_USER        - SMTP login username
    SMTP_PASSWORD    - SMTP login password / app-password
"""

import os
import json
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEARCH_URL = "https://www.ungm.org/Public/Notice/SearchPublicNotices"
NOTICE_BASE_URL = "https://www.ungm.org/Public/Notice"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.ungm.org/Public/Notice",
    "Origin": "https://www.ungm.org",
}


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def fetch_event_notices(days_back: int = 1) -> list[dict]:
    """Return notices published in the last *days_back* days with 'event' in title."""
    now = datetime.now(timezone.utc)
    published_from = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
    published_to = now.strftime("%Y-%m-%d")

    payload = {
        "title": "event",
        "publishedFrom": published_from,
        "publishedTo": published_to,
        "pageIndex": 0,
        "pageSize": 100,
        "sortField": "PublishedOn",
        "sortOrder": "desc",
    }

    try:
        resp = requests.post(SEARCH_URL, json=payload, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"[ERROR] API request failed: {exc}")
        return []
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Failed to parse JSON response: {exc}")
        return []

    # The API may return a list directly or wrap results in a key
    if isinstance(data, list):
        notices = data
    else:
        notices = (
            data.get("notices")
            or data.get("Notices")
            or data.get("data")
            or []
        )

    print(f"[INFO] Fetched {len(notices)} notice(s) matching 'event' "
          f"published {published_from} - {published_to}")
    return notices


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def _notice_url(notice: dict) -> str:
    ref = notice.get("NoticeId") or notice.get("noticeId") or notice.get("id") or ""
    return f"{NOTICE_BASE_URL}/{ref}" if ref else NOTICE_BASE_URL


def _get(notice: dict, *keys: str, default: str = "N/A") -> str:
    for key in keys:
        val = notice.get(key)
        if val:
            return str(val)
    return default


def build_email_html(notices: list[dict], run_date: str) -> str:
    rows = ""
    for n in notices:
        title = _get(n, "Title", "title")
        published = _get(n, "PublishedOn", "publishedOn", "published")
        deadline = _get(n, "Deadline", "deadline")
        org = _get(n, "Organization", "organization", "AgencyName", "agencyName")
        url = _notice_url(n)
        rows += (
            f"<tr>"
            f"<td><a href='{url}'>{title}</a></td>"
            f"<td>{org}</td>"
            f"<td>{published}</td>"
            f"<td>{deadline}</td>"
            f"</tr>\n"
        )

    return f"""<html>
<body style='font-family:Arial,sans-serif;font-size:14px;'>
<p>Hi Juniper,</p>
<p>The following <strong>event-related tenders</strong> were published on
<a href='https://www.ungm.org/Public/Notice'>UNGM</a>
during the past 24 hours ({run_date} UTC):</p>
<table border='1' cellpadding='6' cellspacing='0'
       style='border-collapse:collapse;width:100%;'>
  <thead>
    <tr style='background:#f2f2f2;'>
      <th align='left'>Title</th>
      <th align='left'>Organization</th>
      <th align='left'>Published</th>
      <th align='left'>Deadline</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
<p style='margin-top:16px;'>
  <a href='https://www.ungm.org/Public/Notice'>View all notices on UNGM</a>
</p>
</body>
</html>"""


def send_email(notices: list[dict]) -> None:
    recipient_email = os.environ["RECIPIENT_EMAIL"]
    sender_email = os.environ["SENDER_EMAIL"]
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"[UNGM] {len(notices)} new event tender(s) - {run_date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg.attach(MIMEText(build_email_html(notices, run_date), "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_password)
        recipients = [r.strip() for r in recipient_email.split(",")]
        server.sendmail(sender_email, recipients, msg.as_string())

    print(f"[INFO] Email sent to {recipient_email} with {len(notices)} notice(s).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    notices = fetch_event_notices(days_back=1)

    if not notices:
        print("[INFO] No matching notices found. No email sent.")
        return

    for n in notices:
        print(f"  - {_get(n, 'Title', 'title')}")

    send_email(notices)


if __name__ == "__main__":
    main()
