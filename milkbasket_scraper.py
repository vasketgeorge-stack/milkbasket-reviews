"""
Milkbasket Play Store Reviews Scraper
--------------------------------------
- Fetches reviews in all major Indian languages
- First run: fetches ALL reviews from Play Store
- Subsequent runs: fetches only new reviews
- Merges with existing CSV on GitHub Gist (no duplicates)
- Uploads updated CSV back to Gist
- Sends email summary via Gmail
- Run daily via GitHub Actions at 9AM IST
"""

import csv
import io
import os
import smtplib
import requests
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google_play_scraper import reviews, Sort

# ============================================================
# CONFIG — reads from environment variables (GitHub Secrets)
# ============================================================
APP_ID          = "com.milkbasket.app"
GITHUB_TOKEN    = os.environ["GITHUB_TOKEN_SECRET"]
GIST_ID         = os.environ["GIST_ID"]
GMAIL_SENDER    = os.environ["GMAIL_SENDER"]
GMAIL_APP_PASS  = os.environ["GMAIL_APP_PASS"]
EMAIL_RECIPIENT = os.environ["EMAIL_RECIPIENT"]

LANGUAGES = ["en", "hi", "mr", "gu", "bn", "ta", "te", "kn", "ml", "pa"]

# ============================================================
# FETCH EXISTING CSV FROM GIST
# ============================================================
def fetch_existing_csv():
    url     = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp    = requests.get(url, headers=headers)
    resp.raise_for_status()

    files = resp.json().get("files", {})
    if not files:
        return {}

    first_file = next(iter(files.values()))
    raw_url    = first_file["raw_url"]
    content    = requests.get(raw_url).text

    reader   = csv.DictReader(io.StringIO(content))
    existing = {}
    for row in reader:
        existing[row["reviewId"]] = row
    return existing

# ============================================================
# SCRAPE NEW REVIEWS FROM PLAY STORE
# ============================================================
def scrape_new_reviews(existing_ids):
    all_reviews = {}

    for lang in LANGUAGES:
        print(f"  Scraping language: {lang}")
        try:
            result, _ = reviews(
                APP_ID,
                lang=lang,
                country="in",
                sort=Sort.NEWEST,
                count=200
            )
            for r in result:
                rid = r["reviewId"]
                if rid not in existing_ids and rid not in all_reviews:
                    all_reviews[rid] = {
                        "reviewId":    rid,
                        "userName":    r.get("userName", ""),
                        "score":       r.get("score", ""),
                        "at":          r.get("at", "").strftime("%Y-%m-%d %H:%M:%S") if r.get("at") else "",
                        "content":     r.get("content", "").replace("\n", " "),
                        "thumbsUpCount": r.get("thumbsUpCount", 0),
                        "replyContent":  (r.get("replyContent") or "").replace("\n", " "),
                        "repliedAt":   r.get("repliedAt", "").strftime("%Y-%m-%d %H:%M:%S") if r.get("repliedAt") else "",
                        "language":    lang,
                    }
        except Exception as e:
            print(f"    Warning: failed for lang={lang}: {e}")

    print(f"  Found {len(all_reviews)} new reviews")
    return all_reviews

# ============================================================
# MERGE
# ============================================================
def merge(existing, scraped):
    merged = {**existing, **scraped}
    new_count = len(scraped)
    return merged, new_count

# ============================================================
# UPLOAD TO GIST
# ============================================================
def upload_to_gist(merged):
    fieldnames = ["reviewId", "userName", "score", "at", "content",
                  "thumbsUpCount", "replyContent", "repliedAt", "language"]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in sorted(merged.values(), key=lambda x: x.get("at", ""), reverse=True):
        writer.writerow({k: row.get(k, "") for k in fieldnames})

    url     = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"}
    payload = {"files": {"milkbasket_reviews.csv": {"content": output.getvalue()}}}

    resp = requests.patch(url, headers=headers, json=payload)
    resp.raise_for_status()
    print(f"  Gist updated. Total reviews: {len(merged)}")

# ============================================================
# SEND EMAIL
# ============================================================
def send_email(merged, new_count):
    total = len(merged)
    today = datetime.now().strftime("%d %b %Y")

    subject = f"Milkbasket Reviews Update — {today} ({new_count} new)"
    body    = f"""Milkbasket Play Store Reviews — Daily Update
================================================
Date          : {today}
New reviews   : {new_count}
Total in DB   : {total}

Dashboard     : https://vasketgeorge-stack.github.io/milkbasket-reviews/

Automated by GitHub Actions.
"""

    msg            = MIMEMultipart()
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        print("  Email sent successfully")
    except Exception as e:
        print(f"  Email failed: {e}")

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  Milkbasket Scraper — {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*50}\n")

    try:
        existing            = fetch_existing_csv()
        scraped             = scrape_new_reviews(set(existing.keys()))
        merged, new_count   = merge(existing, scraped)
        upload_to_gist(merged)
        send_email(merged, new_count)
        print("\nDone.\n")
    except Exception as e:
        print(f"\nScript failed: {e}")
        raise
