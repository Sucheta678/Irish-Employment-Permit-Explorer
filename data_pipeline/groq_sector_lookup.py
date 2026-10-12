r"""
Find the sector of still-Unknown companies by web search, using a free Groq API key
(default model openai/gpt-oss-120b with Groq's built-in browser_search tool).

Setup (PowerShell):
    pip install groq pandas
    $env:GROQ_API_KEY = "your-key-here"       # never put the key in code or Git

Test on 5 companies first, then open data\processed\sector_lookup_groq.csv and compare
each answer with its source_url:
    python data_pipeline\groq_sector_lookup.py --limit 5

Then run more. It resumes: companies already searched are skipped. Free limits are small
(about 250 requests/day as of 2026 - check your Groq console), so it stops cleanly when the
daily limit is hit and you can run it again the next day:
    python data_pipeline\groq_sector_lookup.py --limit 200

Input : data/processed/permits_final.csv      (output of apply_name_rules.py)
Output: data/processed/sector_lookup_groq.csv  every answer, with evidence + source URL
        data/processed/permits_complete.csv    permits_final.csv + sectors found by web search
                                               (sector_source = web_llm)

Safety gates - an answer is applied ONLY if all are true:
  - sector is one of the 21 NACE sections
  - confidence >= --min-confidence (default medium)
  - the model says the company is the one operating in Ireland
  - a source URL is given
Everything else stays Unknown and is flagged for manual review in the lookup file.
"""
import argparse
import os
import re
import json
import time
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
CONF_RANK = {"low": 0, "medium": 1, "high": 2}
COLS = [
    "employer_name", "sector_code", "sector", "confidence", "in_ireland",
    "company_found", "what_it_does", "source_url", "all_urls", "error",
]


class DailyLimit(Exception):
    pass


def build_prompt(name, cro_name):
    sections = "\n".join(f"{k}: {v}" for k, v in SECTIONS.items())
    hint = f'\nIts registered name in the Irish company register may be: "{cro_name}".' if isinstance(cro_name, str) and cro_name else ""
    return f"""This employer holds Irish employment permits (2026): "{name}".{hint}
Search the web to find what this organisation mainly does, then classify it into ONE
NACE Rev.2 section from this list:

{sections}

Rules:
- You MUST search the web before answering. Use only what you find in search results.
  Do not answer from memory or guess from the name alone.
- It must be the organisation operating in Ireland. If you cannot tell which company it is,
  or results are about a different company with a similar name, answer UNKNOWN.
- Choose the section for its MAIN activity (a hospital is Q, a restaurant is I).
- confidence: "high" = official or company site clearly states the activity;
  "medium" = a reliable directory or news site confirms it; "low" = unclear or conflicting.

End your reply with ONLY one JSON object on the last line, nothing after it:
{{"section_letter": "<A-U or UNKNOWN>", "company_found": "<name of the organisation you found>", "in_ireland": <true or false>, "what_it_does": "<one short sentence>", "confidence": "<high|medium|low>", "source_url": "<url you relied on>"}}"""


def tool_urls(msg):
    """Collect URLs of the pages the web search used (defensive: format may vary)."""
    urls = []
    try:
        for t in getattr(msg, "executed_tools", None) or []:
            sr = getattr(t, "search_results", None)
            for r in (getattr(sr, "results", None) or []):
                u = getattr(r, "url", None)
                if u:
                    urls.append(u)
    except Exception:
        pass
    return urls


def lookup_one(client, groq, model, row):
    out = {c: "" for c in COLS}
    out["employer_name"] = row["employer_name"]
    for attempt in range(3):
        try:
            extra = {}
            if model.startswith("openai/gpt-oss"):
                # built-in web search; "low" reasoning keeps it fast and cheap on tokens
                extra = {"tools": [{"type": "browser_search"}], "reasoning_effort": "low"}
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[{"role": "user", "content": build_prompt(row["employer_name"], row.get("cro_name"))}],
                **extra,
            )
            msg = resp.choices[0].message
            objs = re.findall(r"\{[^{}]*\}", msg.content or "")
            if not objs:
                raise ValueError("no JSON in reply")
            data = json.loads(objs[-1])
            letter = str(data.get("section_letter", "")).strip().upper()
            conf = str(data.get("confidence", "low")).strip().lower()
            out["confidence"] = conf if conf in CONF_RANK else "low"
            out["in_ireland"] = str(data.get("in_ireland", "")).strip().lower()
            out["company_found"] = str(data.get("company_found", ""))[:150]
            out["what_it_does"] = str(data.get("what_it_does", ""))[:300]
            out["source_url"] = str(data.get("source_url", ""))
            out["all_urls"] = " | ".join(dict.fromkeys(tool_urls(msg)))[:1000]
            if letter in SECTIONS:
                out["sector_code"], out["sector"] = letter, SECTIONS[letter]
            return out
        except (groq.AuthenticationError, groq.NotFoundError, groq.PermissionDeniedError) as e:
            raise SystemExit(f"Groq error that retrying will not fix: {type(e).__name__}: {e}")
        except groq.RateLimitError as e:
            text = str(e).lower()
            if "per day" in text or "tpd" in text or "rpd" in text:
                raise DailyLimit(str(e)[:200])
            out["error"] = "rate limited"
            time.sleep(20 * (attempt + 1))
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"[:200]
            time.sleep(5 * (attempt + 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=Path("data/processed/permits_final.csv"))
    ap.add_argument("--lookup", type=Path, default=Path("data/processed/sector_lookup_groq.csv"))
    ap.add_argument("--output", type=Path, default=Path("data/processed/permits_complete.csv"))
    ap.add_argument("--limit", type=int, default=5, help="how many Unknown companies to search (biggest first)")
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    ap.add_argument("--sleep", type=float, default=3.0, help="seconds between requests (free tier: ~30/min max)")
    ap.add_argument("--min-confidence", choices=["low", "medium", "high"], default="medium")
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    done = set(pd.read_csv(args.lookup)["employer_name"]) if args.lookup.exists() else set()
    todo = (
        df[(df["sector"] == "Unknown") & (~df["employer_name"].isin(done))]
        .sort_values("permits_total", ascending=False)
        .head(args.limit)
    )
    print(f"{len(done)} already searched; searching {len(todo)} more with {args.model}")

    if len(todo):
        if not os.environ.get("GROQ_API_KEY"):
            raise SystemExit('Set your key first:  $env:GROQ_API_KEY = "..."')
        import groq  # imported here so --limit 0 works without the package
        client = groq.Groq()
        args.lookup.parent.mkdir(parents=True, exist_ok=True)
        new_file = not args.lookup.exists()
        with args.lookup.open("a", newline="", encoding="utf-8") as f:
            if new_file:
                f.write(",".join(COLS) + "\n")
            for i, row in enumerate(todo.to_dict("records"), 1):
                try:
                    res = lookup_one(client, groq, args.model, row)
                except DailyLimit as e:
                    print(f"\nDaily Groq limit reached - stopping. Run again tomorrow. ({e})")
                    break
                pd.DataFrame([res], columns=COLS).to_csv(f, header=False, index=False)
                f.flush()
                print(f"[{i}/{len(todo)}] {res['employer_name'][:45]:45} -> {res['sector'] or 'UNKNOWN'} ({res['confidence'] or res['error'][:40]})")
                time.sleep(args.sleep)

    # ---- merge: only fill rows that are still Unknown ----
    out = df.copy()
    if "sector_source" not in out.columns:
        out["sector_source"] = out["sector"].map(lambda s: "none" if s == "Unknown" else "CRO")
    n_filled = 0
    if args.lookup.exists():
        lk = pd.read_csv(args.lookup, dtype=str).fillna("")  # dtype=str: keeps "true" as text, not a bool
        ok = lk[
            (lk["sector"] != "")
            & (lk["confidence"].map(CONF_RANK).fillna(0) >= CONF_RANK[args.min_confidence])
            & (lk["in_ireland"] == "true")
            & (lk["source_url"] != "")
        ].drop_duplicates("employer_name").set_index("employer_name")
        mask = (out["sector"] == "Unknown") & out["employer_name"].isin(ok.index)
        out.loc[mask, "sector_code"] = out.loc[mask, "employer_name"].map(ok["sector_code"])
        out.loc[mask, "sector"] = out.loc[mask, "employer_name"].map(ok["sector"])
        out.loc[mask, "sector_source"] = "web_llm"
        n_filled = int(mask.sum())
        review = len(lk) - len(ok)
    else:
        review = 0
    out.to_csv(args.output, index=False)

    tot = out["permits_total"].sum()
    known = out["sector"] != "Unknown"
    print(f"\nFilled by web search: {n_filled} companies")
    print(f"Permits with a known sector: {out.loc[known, 'permits_total'].sum() / tot:.1%}")
    print(f"Searched but NOT applied (unclear / low confidence / wrong company): {review} -> see {args.lookup}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()