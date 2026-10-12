r"""
Low-token sector lookup for companies that are still Unknown.

How it saves tokens: the web search is done by a free search package (DuckDuckGo), not by
the AI model. The model only reads 5 short snippets (about 600 tokens per company instead of
many thousands) and picks a sector. The source URL comes from the real search results, so
every link can be checked.

Setup (PowerShell):
    pip install groq ddgs pandas
    $env:GROQ_API_KEY = "your-key-here"       # never put the key in code or Git

Test on 5 first and check the links:
    python data_pipeline\sector_lite.py --limit 5

Then run more. Only companies with at least --min-permits permits are searched (default 5),
biggest first, because small companies add little coverage:
    python data_pipeline\sector_lite.py --limit 200

If you hit the daily limit on one model, limits are normally counted per model, so try:
    python data_pipeline\sector_lite.py --limit 200 --model openai/gpt-oss-120b

Input / output: data/processed/permits_complete.csv (updated in place; re-running is safe)
Evidence file : data/processed/sector_lookup_lite.csv (one row per company searched)
sector_source = web_snippets for the sectors this script fills.
"""
import argparse
import json
import os
import re
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
COLS = ["employer_name", "sector_code", "sector", "confidence", "what_it_does", "source_url", "error"]

SHORT_LIST = (
    "A Agriculture; B Mining; C Manufacturing; D Energy supply; E Water/waste; F Construction; "
    "G Wholesale/retail; H Transport/storage; I Hotels/food service; J IT/communications; "
    "K Finance/insurance; L Real estate; M Professional/scientific/technical; "
    "N Admin/support (staffing, cleaning, security); O Public administration; P Education; "
    "Q Health/social care; R Arts/sport/recreation; S Other services; T Households; U Extraterritorial"
)


class DailyLimit(Exception):
    pass


def search_query(name: str) -> str:
    s = re.sub(r"\b(unlimited company|designated activity company|limited|ltd|dac|uc|teoranta)\b", " ", name, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,.-")
    return f"{s} Ireland company"


def web_search(name: str, n: int = 5):
    from ddgs import DDGS
    results = DDGS().text(search_query(name), region="ie-en", max_results=n)
    return [
        {"title": (r.get("title") or "")[:90], "body": (r.get("body") or "")[:220], "url": r.get("href") or ""}
        for r in results or []
    ]


def build_prompt(name: str, results) -> str:
    lines = "\n".join(f"[{i}] {r['title']} - {r['body']}" for i, r in enumerate(results, 1))
    return f"""Company: "{name}" (holds Irish work permits).
Search results:
{lines}

Using ONLY these results, choose the sector of the company's main activity.
Sectors: {SHORT_LIST}
If the results are not clearly about this company in Ireland, answer UNKNOWN.
Reply with only JSON: {{"s":"<letter or UNKNOWN>","c":"<high|medium|low>","r":<number of the result you relied on>,"d":"<max 12 words on what it does>"}}"""


def classify(client, model: str, name: str, results, groq):
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                max_completion_tokens=800,
                messages=[{"role": "user", "content": build_prompt(name, results)}],
                **({"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}),
            )
            objs = re.findall(r"\{[^{}]*\}", resp.choices[0].message.content or "")
            if not objs:
                raise ValueError("no JSON in reply")
            return json.loads(objs[-1])
        except (groq.AuthenticationError, groq.NotFoundError, groq.PermissionDeniedError) as e:
            raise SystemExit(f"Groq error that retrying will not fix: {type(e).__name__}: {e}")
        except groq.RateLimitError as e:
            text = str(e).lower()
            if "per day" in text or "tpd" in text or "rpd" in text:
                raise DailyLimit(str(e)[:200])
            time.sleep(20 * (attempt + 1))
        except Exception:
            time.sleep(3 * (attempt + 1))
    raise ValueError("model call failed")


def lookup_one(client, groq, model, name):
    out = {c: "" for c in COLS}
    out["employer_name"] = name
    try:
        results = web_search(name)
    except Exception as e:
        out["error"] = f"search failed: {type(e).__name__}"
        return out
    if not results:
        out["error"] = "no search results"
        return out
    try:
        data = classify(client, model, name, results, groq)
    except DailyLimit:
        raise
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:150]
        return out

    letter = str(data.get("s", "")).strip().upper()
    conf = str(data.get("c", "low")).strip().lower()
    out["confidence"] = conf if conf in CONF_RANK else "low"
    out["what_it_does"] = str(data.get("d", ""))[:200]
    try:
        idx = int(data.get("r"))
        if 1 <= idx <= len(results):
            out["source_url"] = results[idx - 1]["url"]
    except (TypeError, ValueError):
        pass
    if letter in SECTIONS:
        out["sector_code"], out["sector"] = letter, SECTIONS[letter]
    return out


def merge(df: pd.DataFrame, lookup_path: Path, min_conf: str):
    out = df.copy()
    if "sector_source" not in out.columns:
        out["sector_source"] = out["sector"].map(lambda s: "none" if s == "Unknown" else "CRO")
    if not lookup_path.exists():
        return out, 0, 0
    lk = pd.read_csv(lookup_path, dtype=str).fillna("")
    ok = lk[
        (lk["sector"] != "")
        & (lk["source_url"] != "")
        & (lk["confidence"].map(CONF_RANK).fillna(0) >= CONF_RANK[min_conf])
    ].drop_duplicates("employer_name").set_index("employer_name")
    mask = (out["sector"] == "Unknown") & out["employer_name"].isin(ok.index)
    out.loc[mask, "sector_code"] = out.loc[mask, "employer_name"].map(ok["sector_code"])
    out.loc[mask, "sector"] = out.loc[mask, "employer_name"].map(ok["sector"])
    out.loc[mask, "sector_source"] = "web_snippets"
    return out, int(mask.sum()), len(lk) - len(ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=Path("data/processed/permits_complete.csv"))
    ap.add_argument("--lookup", type=Path, default=Path("data/processed/sector_lookup_lite.csv"))
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--min-permits", type=int, default=5, help="skip companies with fewer permits")
    ap.add_argument("--model", default="openai/gpt-oss-20b")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between companies")
    ap.add_argument("--min-confidence", choices=["low", "medium", "high"], default="medium")
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    done = set(pd.read_csv(args.lookup, dtype=str)["employer_name"]) if args.lookup.exists() else set()
    pool = df[(df["sector"] == "Unknown") & (df["permits_total"] >= args.min_permits) & (~df["employer_name"].isin(done))]
    todo = pool.sort_values("permits_total", ascending=False).head(args.limit)
    print(f"{len(pool)} companies with >= {args.min_permits} permits still to search; searching {len(todo)} now ({args.model})")

    if len(todo):
        if not os.environ.get("GROQ_API_KEY"):
            raise SystemExit('Set your key first:  $env:GROQ_API_KEY = "..."')
        import groq
        client = groq.Groq()
        args.lookup.parent.mkdir(parents=True, exist_ok=True)
        new_file = not args.lookup.exists()
        search_fails = 0
        with args.lookup.open("a", newline="", encoding="utf-8") as f:
            if new_file:
                f.write(",".join(COLS) + "\n")
            for i, name in enumerate(todo["employer_name"], 1):
                try:
                    res = lookup_one(client, groq, args.model, name)
                except DailyLimit as e:
                    print(f"\nDaily Groq limit reached - stopping. Run again tomorrow, or try --model. ({e})")
                    break
                pd.DataFrame([res], columns=COLS).to_csv(f, header=False, index=False)
                f.flush()
                print(f"[{i}/{len(todo)}] {name[:45]:45} -> {res['sector'] or 'UNKNOWN'} ({res['confidence'] or res['error'][:40]})")
                search_fails = search_fails + 1 if res["error"].startswith("search failed") else 0
                if search_fails >= 5:
                    print("\n5 searches in a row failed (DuckDuckGo is probably rate limiting). Wait a while and run again.")
                    break
                time.sleep(args.sleep)

    final, n_filled, n_review = merge(pd.read_csv(args.input), args.lookup, args.min_confidence)
    final.to_csv(args.input, index=False)
    tot = final["permits_total"].sum()
    known = final["sector"] != "Unknown"
    print(f"\nFilled by snippet search: {n_filled} companies")
    print(f"Permits with a known sector: {final.loc[known, 'permits_total'].sum() / tot:.1%}")
    print(f"Searched but NOT applied (unclear / low confidence / no link): {n_review} -> see {args.lookup}")
    print(f"Saved: {args.input}")


if __name__ == "__main__":
    main()