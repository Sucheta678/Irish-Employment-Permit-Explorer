r"""
Fill the "Unknown" sectors in permits_enriched.csv using simple, readable name rules.
No internet, no API key. Only rows that are still Unknown are touched.

Run from the project root (PowerShell):
    python data_pipeline\apply_name_rules.py

Optional: your own hand-checked list, which always wins over the rules.
Create data\reference\sector_overrides.csv with two columns:
    employer_name,sector_code
    Google Ireland Limited,J
    Tata Consultancy Services Limited,J
(sector_code = NACE section letter A-U) and run:
    python data_pipeline\apply_name_rules.py --overrides data\reference\sector_overrides.csv

Outputs:
    data/processed/permits_final.csv        permits_enriched.csv + filled sectors + sector_source
    data/processed/rule_matches_review.csv  every company filled by a rule, with the keyword
                                            that triggered it, biggest first -> spot-check this
sector_source values: CRO, override, rule, none.
Rules are checked top to bottom and the first match wins (order matters).
"""
import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

SECTIONS = {
    "A": "Agriculture, Forestry and Fishing",
    "B": "Mining and Quarrying",
    "C": "Manufacturing",
    "D": "Electricity, Gas, Steam and Air Conditioning Supply",
    "E": "Water Supply, Sewerage and Waste Management",
    "F": "Construction",
    "G": "Wholesale and Retail Trade",
    "H": "Transportation and Storage",
    "I": "Accommodation and Food Service Activities",
    "J": "Information and Communication",
    "K": "Financial and Insurance Activities",
    "L": "Real Estate Activities",
    "M": "Professional, Scientific and Technical Activities",
    "N": "Administrative and Support Service Activities",
    "O": "Public Administration and Defence",
    "P": "Education",
    "Q": "Human Health and Social Work Activities",
    "R": "Arts, Entertainment and Recreation",
    "S": "Other Service Activities",
    "T": "Activities of Households as Employers",
    "U": "Activities of Extraterritorial Organisations",
}

# (section letter, confidence, regex). First match wins. Names are lower-cased and
# accent-stripped before matching, so write patterns in plain lowercase ASCII.
RULES = [
    # --- named public bodies and large firms ---
    ("D", "high", r"electricity supply board|\besb\b|bord gais|gas networks ireland"),
    ("E", "high", r"uisce eireann|irish water"),
    ("H", "high", r"bus atha cliath|dublin bus|bus eireann|irish bus|iarnrod eireann|irish rail"),
    ("M", "high", r"ernst\s*(&|and)\s*young|\bdeloitte\b|\bkpmg\b|pricewaterhouse|\bpwc\b|grant thornton|\bmazars\b"),
    # --- health: strong keywords first ---
    ("Q", "high", r"\bhse\b|health service executive|\btusla\b|child and family agency|children.?s health ireland|"
                  r"\bhospitals?\b|nursing home|\bclinics?\b|\bdental\b|\bdentists?\b|medical centre|medical practice|"
                  r"residential care|extended care|care home|care facility|care centre"),
    # --- recruitment / staffing agencies (before the weaker health words) ---
    ("N", "medium", r"recruit|staffing|\bagency\b|personnel|resourcing|\blocum\b|\bcpl\b",
     r"estate|advertis|marketing|media|creative|design|insurance|energy"),
    # --- health: weaker keywords ---
    ("Q", "medium", r"\bnursing\b|home ?care|healthcare|health care|health services|senior care|"
                    r"childcare|child care|\bcreche\b|disability services",
     r"\bsystems\b|software|technolog|\bsolutions\b|devices|pharma|diagnostics"),
    # --- hotels and restaurants (before education: "College Green Hotel") ---
    ("I", "high", r"\bhotels?\b|restaurants?|takeaway|\bpizz(a|eria)\b"),
    # --- education (hospitals are already caught above) ---
    ("P", "high", r"\buniversity\b|\bcollege\b|institute of technology|technological university",
     r"\bclub\b|\binns?\b"),
    ("P", "medium", r"\bschools?\b|\bacademy\b|montessori"),
    # --- food, accommodation, hospitality ---
    ("I", "medium", r"\bcafes?\b|\bcoffee\b|\bgrill\b|bistro|\bpubs?\b|\bbars?\b|guest ?house|hospitality|kebab|sushi"),
    # --- construction ---
    ("F", "medium", r"construction|scaffold|builders|building contractors|civil engineering|plumbing|"
                    r"electrical contractors|roofing"),
    # --- transport ---
    ("H", "medium", r"\bcoaches\b|haulage|transport|logistics|freight|courier|\btaxis?\b|airlines?"),
    # --- food manufacturing ---
    ("C", "medium", r"\bmeats?\b|\bbeef\b|\bpork\b|poultry|\bbacon\b|\bdairy\b|bakery|brewery|distillery"),
    # --- finance, property, professional ---
    ("K", "medium", r"\bbank\b|banking|insurance|credit union|financial services|asset management"),
    ("L", "medium", r"real estate|\bproperties\b|estate agents?|lettings"),
    ("M", "medium", r"solicitors?|accountants?|accounting|architects?|veterinary|\bvets?\b|law firm|surveyors"),
    # --- admin and support ---
    ("N", "medium", r"security services|security guards?|cleaning|janitorial"),
    # --- recreation and personal services ---
    ("R", "medium", r"golf club|sports club|football club|\bgym\b|fitness|leisure centre|\bgaa\b"),
    ("S", "medium", r"\bhair\b|beauty|barbers?|salon|\bnails\b|\bchurch\b|\bparish\b"),
    # --- retail and wholesale ---
    ("G", "medium", r"\bmotors\b|\bgarage\b|pharmacy|pharmacies|supermarket|wholesale|cash and carry|\bretail\b"),
    # --- farming ---
    ("A", "medium", r"\bfarms\b|\bfarming\b|agricultural"),
]
COMPILED = [
    (r[0], r[1], re.compile(r[2]), re.compile(r[3]) if len(r) > 3 else None)
    for r in RULES
]


def clean(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def match_rule(name: str):
    s = clean(name)
    for letter, conf, rx, skip in COMPILED:
        m = rx.search(s)
        if m and not (skip and skip.search(s)):
            return letter, conf, m.group(0)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enriched", type=Path, default=Path("data/processed/permits_enriched.csv"))
    ap.add_argument("--overrides", type=Path, default=Path("data/reference/sector_overrides.csv"))
    ap.add_argument("--final", type=Path, default=Path("data/processed/permits_final.csv"))
    ap.add_argument("--review", type=Path, default=Path("data/processed/rule_matches_review.csv"))
    args = ap.parse_args()

    df = pd.read_csv(args.enriched)
    tot = df["permits_total"].sum()
    before = df.loc[df["sector"] != "Unknown", "permits_total"].sum() / tot

    df["sector_source"] = df["sector"].map(lambda s: "none" if s == "Unknown" else "CRO")
    df["rule_keyword"] = ""
    df["rule_confidence"] = ""

    # 1) hand-checked overrides (always win)
    n_over = 0
    if args.overrides.exists():
        ov = pd.read_csv(args.overrides, dtype=str).dropna()
        ov["key"] = ov["employer_name"].str.strip().str.lower()
        ov["sector_code"] = ov["sector_code"].str.strip().str.upper()
        ov = ov[ov["sector_code"].isin(SECTIONS)].drop_duplicates("key").set_index("key")
        keys = df["employer_name"].str.strip().str.lower()
        m = keys.isin(ov.index)
        df.loc[m, "sector_code"] = keys[m].map(ov["sector_code"])
        df.loc[m, "sector"] = df.loc[m, "sector_code"].map(SECTIONS)
        df.loc[m, "sector_source"] = "override"
        n_over = int(m.sum())

    # 2) name rules, only for rows that are still Unknown
    for i in df.index[df["sector"] == "Unknown"]:
        hit = match_rule(df.at[i, "employer_name"])
        if hit:
            letter, conf, kw = hit
            df.at[i, "sector"] = SECTIONS[letter]
            df.at[i, "sector_code"] = letter
            df.at[i, "sector_source"] = "rule"
            df.at[i, "rule_keyword"] = kw
            df.at[i, "rule_confidence"] = conf

    args.final.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.final, index=False)

    rules_df = df[df["sector_source"] == "rule"].sort_values("permits_total", ascending=False)
    rules_df[["employer_name", "permits_total", "sector", "rule_keyword", "rule_confidence"]].to_csv(args.review, index=False)

    after = df.loc[df["sector"] != "Unknown", "permits_total"].sum() / tot
    print(f"Permits with a known sector: {before:.1%} -> {after:.1%}")
    print(f"Filled by overrides: {n_over} companies | by rules: {len(rules_df)} companies")
    print("\nRule matches by sector (companies / permits):")
    print(rules_df.groupby("sector")["permits_total"].agg(["count", "sum"]).sort_values("sum", ascending=False).to_string())
    print("\nBiggest rule matches - CHECK THESE BY HAND:")
    print(rules_df.head(25)[["employer_name", "sector", "rule_keyword", "rule_confidence"]].to_string(index=False))
    print(f"\nSaved: {args.final}\nReview list: {args.review}")


if __name__ == "__main__":
    main()