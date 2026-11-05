"""
Year-aware pipeline for the `employment_permit` table (one row per company per year).

Two commands
------------
  load    Bulk-load a CSV you already have (backfill 2024, 2025, ...).
            python permit_pipeline.py load --year 2024 --csv data/raw/data_2024.csv
          If --csv is omitted, the "csv" path for that year in sources.json is used.

  update  Monthly refresh from the DETE page/file registered for that year.
            python permit_pipeline.py update --year 2027
            python permit_pipeline.py update            (current year)
            python permit_pipeline.py update --all      (every year that has a link)
          Matched companies -> permit_count updated.
          New companies     -> sector/size copied from another year if known,
                               otherwise DuckDuckGo lookup, then inserted.
          Nothing is ever deleted.

Human-in-the-loop for new years
-------------------------------
When the DETE page for a new year goes live (e.g. 2027), add ONE entry to
sources.json. Until you do, `update` stops with a clear message and touches nothing.

    {
      "2027": {"page": "https://.../employment-permit-statistics-2027/"}
    }
  "page" = web page the script scrapes for the company file link
  "file" = direct link to the .xlsx/.csv (use this if scraping fails)
  "csv"  = local CSV for `load`

pip install pandas sqlalchemy pymysql python-dotenv requests beautifulsoup4 openpyxl ddgs

.env: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME  (optional: SOURCES_FILE)
"""

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from ddgs import DDGS
from sqlalchemy import create_engine, text

load_dotenv()

TABLE = "employment_permit"
SOURCES_FILE = Path(os.getenv("SOURCES_FILE", "sources.json"))

# ---- bulk CSV format (left = your CSV columns, right = table columns) ----
COLUMN_MAP = {
    "employer_name": "company_name",
    "permits_total": "permit_count",
    "sector": "sector",
    "size": "size_of_company",
}
FINAL_COLUMNS = ["company_name", "permit_count", "sector", "size_of_company"]

# ---- DETE file format (lowercase on purpose: compared against lowercased headers) ----
TOTAL_COL_HINT = "grand total"
NAME_COL_HINT = "employer name"

MAX_LOOKUPS_PER_RUN = 500
LOOKUP_DELAY_SEC = 3

# Adjust labels so they match the values already in your table.
UNCLASSIFIED = "Unclassified - not found"     # what your 2026 data uses when no sector is found
UNRESOLVED_SECTORS = ("Unknown", UNCLASSIFIED) 

SIZE_BANDS = [(9, "Micro"), (49, "Small"), (249, "Medium"), (10**9, "Large")]

SECTOR_KEYWORDS = {
    "Accommodation and Food Service Activities": ["restaurant", "hotel", "cafe", "takeaway", "catering", "pub ", "hospitality", "bar ", "bakery"],
    "Manufacturing": ["manufactur", "pharmaceutical", "medical device", "factory", "production plant", "food processing"],
    "Human Health and Social Work Activities": ["hospital", "nursing home", "healthcare", "pharmacy", "clinic", "care home", "childcare", "dental", "gp practice"],
    "Wholesale and Retail Trade": ["retail", "supermarket", "wholesale", "shop", "store", "distributor"],
    "Professional, Scientific and Technical Activities": ["consultancy", "accountancy", "legal services", "engineering services", "architect", "research and development", "law firm"],
    "Information and Communication": ["software", "technology", "it services", "saas", "data centre", "telecom", "internet", "digital"],
    "Construction": ["construction", "builder", "civil engineering", "contractor"],
    "Financial and Insurance Activities": ["bank", "insurance", "fund", "asset management", "fintech", "payments", "investment"],
    "Administrative and Support Service Activities": ["recruitment", "staffing", "cleaning services", "security services", "outsourcing", "call centre"],
    "Transportation and Storage": ["logistics", "haulage", "transport", "courier", "freight", "warehouse", "airline"],
    "Agriculture, Forestry and Fishing": ["farm", "agri", "horticulture", "meat processing", "forestry", "fishing", "stud"],
    "Other Service Activities": ["hairdresser", "beauty salon", "barber", "laundry", "repair services", "church", "association"],
    "Arts, Entertainment and Recreation": ["gym", "fitness", "sports club", "theatre", "gaming", "entertainment", "leisure"],
    "Education": ["school", "college", "university", "training provider", "language school"],
    "Real Estate Activities": ["property management", "estate agent", "letting", "real estate"],
    "Water Supply, Sewerage and Waste Management": ["waste", "recycling", "water treatment", "sewerage"],
    "Electricity, Gas, Steam and Air Conditioning Supply": ["electricity", "renewable energy", "wind farm", "solar", "gas supply"],
    "Public Administration and Defence": ["government", "public sector", "council", "defence"],
    "Mining and Quarrying": ["quarry", "mining", "aggregates"],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("permit_pipeline.log"), logging.StreamHandler()],
)
log = logging.getLogger("permits")
HEADERS = {"User-Agent": "Mozilla/5.0 (permit-explorer updater)"}


# ============================================================ shared
def get_engine():
    url = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}"
        f"/{os.getenv('DB_NAME')}?charset=utf8mb4"
    )
    return create_engine(url)


def get_source(year):
    """Return the sources.json entry for a year ({} if none)."""
    if not SOURCES_FILE.exists():
        return {}
    with open(SOURCES_FILE, encoding="utf-8") as f:
        return json.load(f).get(str(year), {})


def all_source_years():
    if not SOURCES_FILE.exists():
        return []
    with open(SOURCES_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    return sorted(int(y) for y, v in cfg.items() if v.get("page") or v.get("file"))


def norm(name):
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"\s*t/a\b.*", "", s)                       # drop "t/a Trading Name"
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(limited|ltd|dac|plc|ulc|unlimited company|designated activity company)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ============================================================ load (CSV backfill)
def load_and_clean(path, year):
    df = pd.read_csv(path)
    log.info("CSV columns found: %s", df.columns.tolist())

    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise KeyError(f"Columns {missing} not in CSV. Edit COLUMN_MAP at the top of this script.")

    df = df.rename(columns=COLUMN_MAP)[FINAL_COLUMNS]

    df["company_name"] = df["company_name"].astype("string").str.strip()
    df = df[df["company_name"].notna() & (df["company_name"] != "")]

    df["permit_count"] = pd.to_numeric(df["permit_count"], errors="coerce")
    bad = df["permit_count"].isna() | (df["permit_count"] < 0)
    if bad.any():
        log.warning("Dropping %d rows with invalid permit_count", bad.sum())
        df = df[~bad]
    df["permit_count"] = df["permit_count"].astype(int)

    for col in ["sector", "size_of_company"]:
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace("", pd.NA).fillna("Unknown")

    dupes = df["company_name"].duplicated().sum()
    if dupes:
        log.info("Combining %d duplicate company names (summing permit_count)", dupes)
        df = df.groupby("company_name", as_index=False).agg(
            permit_count=("permit_count", "sum"),
            sector=("sector", "first"),
            size_of_company=("size_of_company", "first"),
        )

    df["permit_year"] = year
    return df.astype(object).where(df.notna(), None)


def run_load(year, csv_path, engine):
    csv_path = csv_path or get_source(year).get("csv")
    if not csv_path:
        log.error("No CSV given for %s. Pass --csv or add \"csv\" for %s in %s.", year, year, SOURCES_FILE)
        return False

    df = load_and_clean(csv_path, year)
    sql = text(f"""
        INSERT INTO {TABLE} (company_name, permit_year, permit_count, sector, size_of_company)
        VALUES (:company_name, :permit_year, :permit_count, :sector, :size_of_company)
        ON DUPLICATE KEY UPDATE
            permit_count = VALUES(permit_count),
            sector = VALUES(sector),
            size_of_company = VALUES(size_of_company)
    """)
    records = df.to_dict(orient="records")
    with engine.begin() as conn:
        conn.execute(sql, records)
    log.info("Loaded %d rows for %s", len(records), year)
    return True


# ============================================================ update (DETE file)
def find_file_url(entry, year):
    if entry.get("file"):
        return entry["file"]
    page = entry["page"]
    html = requests.get(page, headers=HEADERS, timeout=60).text
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = a["href"]
        label = (a.get_text() + " " + href).lower()
        if re.search(r"\.(xlsx|xls|csv)(\?|$)", href.lower()) and "compan" in label and str(year) in label:
            return urljoin(page, href)
    raise RuntimeError(
        f"No {year} company permit file found on {page}. "
        f"Add a direct link as \"file\" for {year} in {SOURCES_FILE}."
    )


def download_table(url):
    if url.startswith(("http://", "https://")):
        log.info("Downloading %s", url)
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        content = r.content
    else:
        log.info("Reading local file %s", url)
        content = Path(url).read_bytes()
    buf = io.BytesIO(content)
    if url.lower().split("?")[0].endswith(".csv"):
        raw = pd.read_csv(buf, header=None, dtype=str)
    else:
        raw = pd.read_excel(buf, header=None, dtype=str)  # first sheet
    for i in range(min(15, len(raw))):                      # header row isn't always row 0
        vals = raw.iloc[i].astype(str).str.lower()
        if vals.str.contains(TOTAL_COL_HINT, regex=False).any():
            df = raw.iloc[i + 1:].copy()
            df.columns = [str(c).strip() for c in raw.iloc[i]]
            return df
    raise RuntimeError(f"Could not find a header row containing '{TOTAL_COL_HINT}'")


def parse(df):
    name_col = next(c for c in df.columns if NAME_COL_HINT in c.lower())
    total_col = next(c for c in df.columns if TOTAL_COL_HINT in c.lower())
    out = df[[name_col, total_col]].rename(columns={name_col: "company_name", total_col: "permit_count"})
    out["company_name"] = out["company_name"].astype("string").str.strip()
    out = out[out["company_name"].notna() & (out["company_name"] != "")]
    out = out[~out["company_name"].str.contains("grand total", case=False, na=False)]
    out["permit_count"] = pd.to_numeric(out["permit_count"].astype(str).str.replace(",", ""), errors="coerce")
    out = out.dropna(subset=["permit_count"])
    out["permit_count"] = out["permit_count"].astype(int)
    return out.groupby("company_name", as_index=False)["permit_count"].sum()


def size_band(n):
    return next(label for cap, label in SIZE_BANDS if n <= cap)


def lookup(company):
    try:
        results = DDGS().text(f"{company} Ireland company employees industry", max_results=8)
    except Exception as e:
        log.warning("DDG failed for %s: %s", company, e)
        return "Unknown", "Unknown"
    blob = " ".join(f"{r.get('title', '')} {r.get('body', '')}" for r in results).lower()

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


def run_update(year, engine):
    entry = get_source(year)
    if not (entry.get("page") or entry.get("file")):
        log.error(
            "No link registered for %s. Add it to %s, e.g.\n"
            '    "%s": {"page": "https://<DETE statistics page for %s>"}',
            year, SOURCES_FILE, year, year,
        )
        return False

    new = parse(download_table(find_file_url(entry, year)))
    log.info("[%s] file has %d companies", year, len(new))

    with engine.connect() as conn:
        this_year = pd.read_sql(
            text(f"SELECT id, company_name FROM {TABLE} WHERE permit_year = :y"), conn, params={"y": year}
        )
        other_years = pd.read_sql(
            text(f"""SELECT company_name, sector, size_of_company FROM {TABLE}
                     WHERE permit_year <> :y
                       AND sector NOT IN ('Unknown', '{UNCLASSIFIED}')"""),
            conn, params={"y": year},
        )

    id_by_key = {norm(n): i for i, n in zip(this_year["id"], this_year["company_name"])}
    attrs_by_key = {
        norm(n): (s, z)
        for n, s, z in zip(other_years["company_name"], other_years["sector"], other_years["size_of_company"])
    }

    new["key"] = new["company_name"].map(norm)
    new["id"] = new["key"].map(id_by_key)
    matched, unmatched = new[new["id"].notna()], new[new["id"].isna()]
    log.info("[%s] matched %d, new %d", year, len(matched), len(unmatched))

    # 1. update counts for companies already in this year
    if len(matched):
        with engine.begin() as conn:
            conn.execute(
                text(f"UPDATE {TABLE} SET permit_count = :permit_count WHERE id = :id"),
                [{"permit_count": int(r.permit_count), "id": int(r.id)} for r in matched.itertuples()],
            )

    # 2. insert new companies
    #    - known in another year: copy sector/size, no web search, no cap
    #    - otherwise: DuckDuckGo lookup, capped at MAX_LOOKUPS_PER_RUN per run
    inserted = lookups = skipped = 0
    for r in unmatched.itertuples():
        if r.key in attrs_by_key:
            sector, size = attrs_by_key[r.key]
            searched = False
        elif lookups < MAX_LOOKUPS_PER_RUN:
            sector, size = lookup(r.company_name)
            searched = True
            lookups += 1
        else:
            skipped += 1                      # picked up on the next run
            continue

        with engine.begin() as conn:          # commit per row so a crash or Ctrl+C keeps progress
            conn.execute(
                text(f"""INSERT INTO {TABLE} (company_name, permit_year, permit_count, sector, size_of_company)
                         VALUES (:n, :y, :p, :s, :z)
                         ON DUPLICATE KEY UPDATE permit_count = VALUES(permit_count)"""),
                {"n": r.company_name, "y": year, "p": int(r.permit_count), "s": sector, "z": size},
            )
        inserted += 1
        log.info("[%s] added %s | %s | %s%s", year, r.company_name, sector, size,
                 "" if searched else " (from other year)")
        if searched:
            time.sleep(LOOKUP_DELAY_SEC)

    if skipped > 0:
        log.warning("[%s] %d new companies skipped (lookup cap); rerun to continue", year, skipped)
    log.info("[%s] done: %d updated, %d inserted (%d web lookups)", year, len(matched), inserted, lookups)
    return True

def run_refill(year, engine):
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"""SELECT id, company_name, sector, size_of_company FROM {TABLE}
                WHERE permit_year = :y
                  AND (sector IN ('Unknown', '{UNCLASSIFIED}') OR size_of_company = 'Unknown')"""
        ), {"y": year}).fetchall()
        other_years = pd.read_sql(
            text(f"""SELECT company_name, sector, size_of_company FROM {TABLE}
                     WHERE permit_year <> :y
                       AND sector NOT IN ('Unknown', '{UNCLASSIFIED}')"""),
            conn, params={"y": year},
        )
    attrs_by_key = {
        norm(n): (s, z)
        for n, s, z in zip(other_years["company_name"], other_years["sector"], other_years["size_of_company"])
    }
    log.info("[%s] %d rows still have unresolved sector or size", year, len(rows))

    filled = 0
    for id_, name, old_sector, old_size in rows:
        key = norm(name)
        if key in attrs_by_key:                          # known from another year: no search
            sector, size = attrs_by_key[key]
            searched = False
        else:
            sector, size = lookup(name)
            searched = True

        new_sector = sector if (old_sector in UNRESOLVED_SECTORS and sector not in UNRESOLVED_SECTORS) else old_sector
        new_size = size if (old_size == "Unknown" and size != "Unknown") else old_size

        if (new_sector, new_size) != (old_sector, old_size):
            with engine.begin() as conn:                 # commit per row so Ctrl+C keeps progress
                conn.execute(
                    text(f"UPDATE {TABLE} SET sector = :s, size_of_company = :z WHERE id = :id"),
                    {"s": new_sector, "z": new_size, "id": id_},
                )
            filled += 1
            log.info("[%s] filled %s | %s | %s%s", year, name, new_sector, new_size,
                     "" if searched else " (from other year)")
        if searched:
            time.sleep(LOOKUP_DELAY_SEC)

    log.info("[%s] refill done: %d of %d rows improved", year, filled, len(rows))
    return True


# ============================================================ verify + CLI
def verify(engine):
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"""SELECT permit_year, COUNT(*), COALESCE(SUM(permit_count), 0)
                FROM {TABLE} GROUP BY permit_year ORDER BY permit_year"""
        )).fetchall()
    for y, companies, permits in rows:
        log.info("Year %s: %s companies, %s permits", y, companies, permits)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_load = sub.add_parser("load", help="bulk-load a CSV for one year")
    p_load.add_argument("--year", type=int, required=True)
    p_load.add_argument("--csv")

    p_up = sub.add_parser("update", help="refresh from the DETE file/link registered in sources.json")
    p_up.add_argument("--year", type=int, default=date.today().year)
    p_up.add_argument("--all", action="store_true", help="update every year that has a link")

    p_ref = sub.add_parser("refill", help="re-search rows with Unknown/unclassified sector or Unknown size")
    p_ref.add_argument("--year", type=int, required=True)

    args = ap.parse_args()
    engine = get_engine()

    if args.cmd == "load":
        ok = run_load(args.year, args.csv, engine)
    elif args.cmd == "refill":
        ok = run_refill(args.year, engine)
    else:
        years = all_source_years() if args.all else [args.year]
        ok = bool(years) and all([run_update(y, engine) for y in years])

    verify(engine)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()