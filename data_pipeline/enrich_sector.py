"""
Add `sector` and `size` columns to the DETE company permit file by matching
company names against the CRO company register (opendata.cro.ie, "Company Records").

No LLM is used on purpose: name matching + a NACE lookup is deterministic,
free, repeatable, and every result can be checked.

Install:
    pip install pandas openpyxl rapidfuzz

Step 1 - see the CRO columns first (run once, then pass the right names below):
    python data/raw/enrich.py --cro data/raw/permits-issued-to-companies-2026.xlsx --show-columns

Step 2 - run the enrichment:
    python data_pipeline/enrich_sector.py \
        --permits data/raw/permits-issued-to-companies-2026.xlsx \
        --cro data/raw/companies.csv.zip \
        --out data/processed/permits_enriched.csv

Optional overrides if auto-detection picks the wrong CRO column:
    --cro-name-col, --cro-nace-col, --cro-status-col, --cro-size-col

NOTE on `size`: the CRO register is not expected to hold employee numbers.
If you do not pass --cro-size-col, size is "Unknown" for every company.
Never guess size; add it only from a real source.
"""
import argparse
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

# NACE Rev.2 divisions (first two digits of the code) -> section letter + title
NACE_RANGES = [
    (1, 3, "A", "Agriculture, Forestry and Fishing"),
    (5, 9, "B", "Mining and Quarrying"),
    (10, 33, "C", "Manufacturing"),
    (35, 35, "D", "Electricity, Gas, Steam and Air Conditioning Supply"),
    (36, 39, "E", "Water Supply, Sewerage and Waste Management"),
    (41, 43, "F", "Construction"),
    (45, 47, "G", "Wholesale and Retail Trade"),
    (49, 53, "H", "Transportation and Storage"),
    (55, 56, "I", "Accommodation and Food Service Activities"),
    (58, 63, "J", "Information and Communication"),
    (64, 66, "K", "Financial and Insurance Activities"),
    (68, 68, "L", "Real Estate Activities"),
    (69, 75, "M", "Professional, Scientific and Technical Activities"),
    (77, 82, "N", "Administrative and Support Service Activities"),
    (84, 84, "O", "Public Administration and Defence"),
    (85, 85, "P", "Education"),
    (86, 88, "Q", "Human Health and Social Work Activities"),
    (90, 93, "R", "Arts, Entertainment and Recreation"),
    (94, 96, "S", "Other Service Activities"),
    (97, 98, "T", "Activities of Households as Employers"),
    (99, 99, "U", "Activities of Extraterritorial Organisations"),
]

SUFFIX_RE = re.compile(
    r"\b(designated activity company|company limited by guarantee|public limited company|"
    r"unlimited company|limited|ltd|dac|uc|plc|clg|teoranta|teo)\b"
)


def normalise(name: str) -> str:
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = SUFFIX_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def nace_section(code):
    digits = re.sub(r"\D", "", str(code or ""))
    if len(digits) < 2:
        return None, None
    div = int(digits[:2])
    for lo, hi, letter, label in NACE_RANGES:
        if lo <= div <= hi:
            return letter, label
    return None, None


def find_col(cols, *keys, exclude=()):
    for c in cols:
        low = c.lower()
        if all(k in low for k in keys) and not any(e in low for e in exclude):
            return c
    return None


def load_cro(path: Path) -> pd.DataFrame:
    # read_csv handles a single-file .zip directly
    try:
        return pd.read_csv(path, dtype=str, low_memory=False)
    except UnicodeDecodeError:
        return pd.read_csv(path, dtype=str, low_memory=False, encoding="latin-1")


def build_lookup(cro, name_col, nace_col, status_col, size_col):
    """normalised name -> one record. If several active CRO companies share a
    name and have different sectors, mark it ambiguous (sector stays Unknown)."""
    df = pd.DataFrame({"name": cro[name_col]})
    df["norm"] = df["name"].map(normalise)
    df["nace"] = cro[nace_col] if nace_col else None
    df["status"] = cro[status_col] if status_col else ""
    df["size"] = cro[size_col] if size_col else None
    df = df[df["norm"] != ""]

    sec = df["nace"].map(nace_section)
    df["letter"] = sec.map(lambda t: t[0])
    df["label"] = sec.map(lambda t: t[1])
    df["active"] = df["status"].fillna("").str.contains(r"normal|live|active|registered", case=False)

    lookup = {}
    for norm, g in df.groupby("norm", sort=False):
        cand = g[g["active"]] if g["active"].any() else g
        letters = set(cand["letter"].dropna())
        row = cand.iloc[0]
        if len(letters) == 1:
            row = cand[cand["letter"].notna()].iloc[0]
        lookup[norm] = {
            "cro_name": row["name"],
            "nace": row["nace"],
            "letter": row["letter"] if len(letters) == 1 else None,
            "label": row["label"] if len(letters) == 1 else None,
            "size": row["size"],
            "ambiguous": len(letters) > 1,
        }
    return lookup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--permits", type=Path)
    ap.add_argument("--cro", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/processed/permits_enriched.csv"))
    ap.add_argument("--show-columns", action="store_true")
    ap.add_argument("--cro-name-col")
    ap.add_argument("--cro-nace-col")
    ap.add_argument("--cro-status-col")
    ap.add_argument("--cro-size-col")
    ap.add_argument("--fuzzy-threshold", type=int, default=93)
    args = ap.parse_args()

    cro = load_cro(args.cro)
    cols = list(cro.columns)
    if args.show_columns:
        print("CRO columns:", cols)
        print(cro.head(3).T.to_string())
        return

    name_col = args.cro_name_col or find_col(cols, "company", "name", exclude=("former", "prev")) or find_col(cols, "name", exclude=("former", "prev"))
    nace_col = args.cro_nace_col or find_col(cols, "nace")
    status_col = args.cro_status_col or find_col(cols, "status")
    size_col = args.cro_size_col
    print(f"Using CRO columns -> name: {name_col} | nace: {nace_col} | status: {status_col} | size: {size_col}")
    if not name_col:
        raise SystemExit("Could not find the CRO company-name column; pass --cro-name-col")
    if not nace_col:
        print("WARNING: no NACE column found; every sector will be Unknown. Pass --cro-nace-col if it exists.")

    lookup = build_lookup(cro, name_col, nace_col, status_col, size_col)
    blocks = defaultdict(list)
    for n in lookup:
        blocks[n.split(" ", 1)[0]].append(n)

    # permit file: header in row 0, last row is a 'Total' row
    permits = pd.read_excel(args.permits, sheet_name=0)
    name_p = permits.columns[0]
    total_col = [c for c in permits.columns if "grand total" in str(c).lower()][0]
    permits = permits[permits[name_p].notna() & (permits[name_p].astype(str).str.strip().str.lower() != "total")].copy()
    permits["permits_total"] = pd.to_numeric(permits[total_col], errors="coerce").fillna(0).astype(int)

    results = []
    for emp, total in zip(permits[name_p], permits["permits_total"]):
        norm = normalise(emp)
        rec, quality = lookup.get(norm), "exact"
        if rec is None and norm:
            cands = blocks.get(norm.split(" ", 1)[0], [])
            hit = process.extractOne(norm, cands, scorer=fuzz.token_sort_ratio, score_cutoff=args.fuzzy_threshold) if cands else None
            if hit:
                rec, quality = lookup[hit[0]], "close"
        if rec is None:
            quality = "none"
        elif rec["ambiguous"]:
            quality = "ambiguous"
        results.append({
            "employer_name": emp,
            "permits_total": total,
            "sector": (rec or {}).get("label") or "Unknown",
            "sector_code": (rec or {}).get("letter"),
            "size": (rec or {}).get("size") if size_col and rec and pd.notna(rec.get("size")) else "Unknown",
            "match_quality": quality,
            "cro_name": (rec or {}).get("cro_name"),
            "nace_code": (rec or {}).get("nace"),
        })

    out = pd.DataFrame(results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    # ---- coverage report: this tells you whether the data is trustworthy ----
    n, tot = len(out), out["permits_total"].sum()
    known = out["sector"] != "Unknown"
    print(f"\nCompanies: {n} | with sector: {known.sum()} ({known.mean():.1%})")
    print(f"Permits covered by a known sector: {out.loc[known, 'permits_total'].sum() / tot:.1%}")
    print("\nMatch quality:\n", out["match_quality"].value_counts().to_string())
    print("\nPermits by sector:\n", out.groupby("sector")["permits_total"].sum().sort_values(ascending=False).to_string())
    print("\nTop 25 employers still Unknown (check these by hand):")
    print(out[~known].nlargest(25, "permits_total")[["employer_name", "permits_total", "match_quality"]].to_string(index=False))
    print("\nTop 25 'close' matches (spot-check these too):")
    print(out[out["match_quality"] == "close"].nlargest(25, "permits_total")[["employer_name", "cro_name", "permits_total"]].to_string(index=False))
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()