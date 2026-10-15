"""
Monthly refresh of employment_permit_2026 from the DETE permits file.

1. Finds the latest "permits issued to companies" file on the DETE statistics page and downloads it.
2. Matches company names against the DB (normalised, so "Google Ireland Ltd." == "GOOGLE IRELAND LIMITED").
   - match  -> SET permit_count = Permits Issued Grand Total
   - no match -> DuckDuckGo lookup for sector + approximate size, then INSERT
3. Never deletes anything. Companies missing from the new file are left untouched.

pip install pandas sqlalchemy pymysql python-dotenv requests beautifulsoup4 openpyxl ddgs

Extra .env keys (optional):
    DETE_STATS_URL=<the DETE employment permit statistics page>
    DETE_FILE_URL=<direct file link, skips the page scraping>
"""

import io
import logging
import os
import re
import time
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from ddgs import DDGS
from sqlalchemy import create_engine, text

load_dotenv()
TABLE = "employment_permit_2026"
YEAR = date.today().year
STATS_URL = os.getenv("DETE_STATS_URL", "")          # set this in .env
DIRECT_URL = os.getenv("DETE_FILE_URL", "")          # optional override
TOTAL_COL_HINT = "Permits Issued Grand Total"                       # matches "Permits Issued Grand Total"
NAME_COL_HINT = "Employer Name"                           # matches "Employer Name" etc.
MAX_LOOKUPS_PER_RUN = 500
LOOKUP_DELAY_SEC = 3                                 # be polite, avoids DDG rate limits

# Adjust the labels on the right so they match the values already in your table.
SIZE_BANDS = [(10, "1-10"), (50, "11-50"), (250, "51-250"), (1000, "251-1000"), (10**9, "1000+")]
SECTOR_KEYWORDS = {
    "Information & Communication": ["software", "technology", "it services", "saas", "data centre", "telecom", "internet"],
    "Health & Social Work": ["hospital", "nursing home", "healthcare", "pharmacy", "medical", "care home", "clinic"],
    "Accommodation & Food": ["restaurant", "hotel", "cafe", "takeaway", "catering", "pub ", "hospitality"],
    "Financial & Insurance": ["bank", "insurance", "fund", "asset management", "fintech", "payments"],
    "Manufacturing": ["manufactur", "pharmaceutical", "medical device", "factory"],
    "Construction": ["construction", "builder", "civil engineering"],
    "Wholesale & Retail": ["retail", "supermarket", "wholesale", "shop", "store"],
    "Education": ["school", "college", "university", "training provider", "language school"],
    "Agriculture": ["farm", "agri", "horticulture", "meat processing"],
    "Transport & Storage": ["logistics", "haulage", "transport", "courier", "freight"],
    "Professional & Technical": ["consultancy", "accountancy", "legal services", "engineering services", "architect"],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("monthly_update.log"), logging.StreamHandler()],
)
log = logging.getLogger("monthly")
HEADERS = {"User-Agent": "Mozilla/5.0 (permit-explorer monthly updater)"}


def get_engine():
    url = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}"
        f"/{os.getenv('DB_NAME')}?charset=utf8mb4"
    )
    return create_engine(url)


# ---------- 1. download ----------
def find_file_url():
    if DIRECT_URL:
        return DIRECT_URL
    if not STATS_URL:
        raise RuntimeError("Set DETE_STATS_URL (or DETE_FILE_URL) in .env")
    html = requests.get(STATS_URL, headers=HEADERS, timeout=60).text
    links = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = a["href"]
        label = (a.get_text() + " " + href).lower()
        if re.search(r"\.(xlsx|xls|csv)(\?|$)", href.lower()) and "compan" in label and str(YEAR) in label:
            links.append(requests.compat.urljoin(STATS_URL, href))
    if not links:
        raise RuntimeError(f"No {YEAR} company permit file link found on {STATS_URL}")
    return links[0]


def download_table(url):
    log.info("Downloading %s", url)
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    buf = io.BytesIO(r.content)
    if url.lower().split("?")[0].endswith(".csv"):
        raw = pd.read_csv(buf, header=None, dtype=str)
    else:
        raw = pd.read_excel(buf, header=None, dtype=str)   # first sheet
    # header row isn't always row 0: find the row that contains the total column
    for i in range(min(15, len(raw))):
        vals = raw.iloc[i].astype(str).str.lower()
        if vals.str.contains(TOTAL_COL_HINT).any():
            df = raw.iloc[i + 1:].copy()
            df.columns = [str(c).strip() for c in raw.iloc[i]]
            return df
    raise RuntimeError("Could not find a header row containing 'Grand Total'")


def parse(df):
    name_col = next(c for c in df.columns if NAME_COL_HINT in c.lower())
    total_col = next(c for c in df.columns if TOTAL_COL_HINT in c.lower())
    out = df[[name_col, total_col]].rename(columns={name_col: "company_name", total_col: "permit_count"})
    out["company_name"] = out["company_name"].astype("string").str.strip()
    out = out[out["company_name"].notna() & (out["company_name"] != "")]
    out = out[~out["company_name"].str.contains("grand total", case=False, na=False)]  # drop totals row
    out["permit_count"] = pd.to_numeric(out["permit_count"].astype(str).str.replace(",", ""), errors="coerce")
    out = out.dropna(subset=["permit_count"])
    out["permit_count"] = out["permit_count"].astype(int)
    return out.groupby("company_name", as_index=False)["permit_count"].sum()


# ---------- 2. matching ----------
def norm(name):
    s = re.sub(r"[^a-z0-9 ]", " ", str(name).lower().replace("&", " and "))
    s = re.sub(r"\b(limited|ltd|dac|plc|ulc|unlimited company|designated activity company|t/a.*)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- 3. DuckDuckGo lookup ----------
def size_band(n):
    return next(label for cap, label in SIZE_BANDS if n <= cap)


def lookup(company):
    try:
        results = DDGS().text(f"{company} Ireland company employees industry", max_results=8)
    except Exception as e:
        log.warning("DDG failed for %s: %s", company, e)
        return "Unknown", "Unknown"
    blob = " ".join(f"{r.get('title','')} {r.get('body','')}" for r in results).lower()

    sector = "Unknown"
    scores = {s: sum(blob.count(k) for k in kws) for s, kws in SECTOR_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        sector = best

    size = "Unknown"
    nums = [int(m.replace(",", "")) for m in re.findall(r"(\d[\d,]*)\+?\s*(?:employees|staff|people)", blob)]
    if nums:
        size = size_band(nums[0])
    return sector, size


# ---------- 4. main ----------
def run():
    new = parse(download_table(find_file_url()))
    log.info("File has %d companies", len(new))
    engine = get_engine()

    with engine.connect() as conn:
        existing = pd.read_sql(text(f"SELECT id, company_name FROM {TABLE}"), conn)
    lookup_map = {norm(n): i for i, n in zip(existing["id"], existing["company_name"])}

    new["key"] = new["company_name"].map(norm)
    new["id"] = new["key"].map(lookup_map)
    matched, unmatched = new[new["id"].notna()], new[new["id"].isna()]
    log.info("Matched %d, new %d", len(matched), len(unmatched))

    with engine.begin() as conn:
        if len(matched):
            conn.execute(
                text(f"UPDATE {TABLE} SET permit_count = :permit_count WHERE id = :id"),
                [{"permit_count": int(r.permit_count), "id": int(r.id)} for r in matched.itertuples()],
            )

    inserted = 0
    for r in unmatched.head(MAX_LOOKUPS_PER_RUN).itertuples():
        sector, size = lookup(r.company_name)
        with engine.begin() as conn:       # commit per row so a crash keeps progress
            conn.execute(
                text(f"""INSERT INTO {TABLE} (company_name, permit_count, sector, size_of_company)
                         VALUES (:n, :p, :s, :z)
                         ON DUPLICATE KEY UPDATE permit_count = VALUES(permit_count)"""),
                {"n": r.company_name, "p": int(r.permit_count), "s": sector, "z": size},
            )
        inserted += 1
        log.info("Added %s | %s | %s", r.company_name, sector, size)
        time.sleep(LOOKUP_DELAY_SEC)

    skipped = len(unmatched) - inserted
    if skipped > 0:
        log.warning("%d new companies skipped (lookup cap); they'll be picked up next run", skipped)
    log.info("Done: %d updated, %d inserted", len(matched), inserted)


if __name__ == "__main__":
    run()