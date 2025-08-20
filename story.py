#!/usr/bin/env python
# ---------------------------------------------------------------------------
#  DIW-StoryLab  –  one-file prototype
#  ---------------------------------------------------------------------------
#  1.  extract_text     … pull plain text + page numbers from PDFs
#  2.  clean_text       … basic comma→dot fix for numbers
#  3.  classify_text    … very small keyword map → high-level topics
#  4.  tag_timeline     … Past / Present / Future buckets
#  5.  make_story       … Llama-cpp generates Past–Present–Future narrative
#  6.  write_stories    … one file per topic  (.txt)
#
#  Usage examples
#  --------------
#     python storylab.py extract      # just text
#     python storylab.py story        # assumes earlier steps ran
#     python storylab.py all          # full chain in one go
#
#  Requirements (pip install …)
#  ----------------------------
#     pdfplumber  pandas  regex  dateparser  llama-cpp-python[all]
#     fitz==PyMuPDF  tqdm
# ---------------------------------------------------------------------------

from pathlib import Path
import re, sys, json, shutil, subprocess
import pandas as pd
import pdfplumber, fitz
import regex as re2
import dateparser
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"            # put PDFs here
OUT  = ROOT / "out"             # results land here
OUT.mkdir(exist_ok=True)


def with_cite(row):
    """Return 'text (filename p.X)' for the LLM prompt."""
    cite = f"{row.file} p.{row.page}"
    return f"{row.text} ({cite})"

def overlap_snippets(topic_a: str, topic_b: str, df: pd.DataFrame):
    """
    Return a list of dicts — one per (file, page) where *both* topics occur.
    Each dict →  {'file':…, 'page':…, 'snippets': [txtA, txtB, …]}
    """
    # keep only rows we care about
    sub = df[df.topic.isin([topic_a, topic_b])]
    # group by file & page
    both = []
    for (f, p), grp in sub.groupby(["file", "page"]):
        if {topic_a, topic_b}.issubset(set(grp.topic)):
            both.append({
                "file": f, "page": p,
                "snippets": grp.sort_values("topic")["text"].tolist()
            })
    return both

# ---------------------------------------------------------------------------
# 1 · TEXT EXTRACTION
# ---------------------------------------------------------------------------
def extract_text():
    rows = []
    for pdf in DATA.glob("*.pdf"):
        with pdfplumber.open(pdf) as doc:
            for p in doc.pages:
                raw = p.extract_text() or ""
                if not raw:
                    continue

                # a) join lines → one string
                # • remove hyphen + LF  (eco-
                #                         nomic → economic)
                # • remove LF between two letters (correla\n tion → correlation)
                text = re.sub(r'-\s*\n\s*', '', raw)        # hyphen-breaks
                text = re.sub(r'(?<=\w)\n(?=\w)', '', text) # wrap-breaks
                text = text.replace('\n', ' ')              # keep paragraph spacing

                # b) split into sentences (cheap regex is fine here)
                sentences = re.split(r'(?<=[.!?])\s{1,}', text)
                for sent in sentences:
                    s = sent.strip()
                    if len(s) > 0:
                        rows.append({
                            "file": pdf.name,
                            "page": p.page_number,
                            "text": s
                        })
    if rows:
        pd.DataFrame(rows).to_parquet(OUT / "sentences.parquet")
        print(f"✅ wrote {len(rows):,} rows to out/sentences.parquet")
    else:
        print("⚠️  No text extracted — check if PDFs exist in data/")

# ---------------------------------------------------------------------------
# 2 · CLEAN
# ---------------------------------------------------------------------------
def clean_text():
    fp_in  = OUT / "sentences.parquet"
    fp_out = OUT / "sentences_clean.parquet"
    if not fp_in.exists():
        print("⚠️  run 'extract' first"); return
    df = pd.read_parquet(fp_in)

    def fix_commas(s: str) -> str:
        s = re.sub(r'(\d),(\d{3})', r'\1\2', s)  # 1,234 → 1234
        return s.replace(",", ".")               # 18,3 → 18.3

    df["text"] = df["text"].map(fix_commas)
    df.to_parquet(fp_out)
    print("✅ cleaned →", fp_out.name)

# ---------------------------------------------------------------------------
# 3 · CLASSIFY  (tiny keyword fallback)
# ---------------------------------------------------------------------------
KEYWORDS = {
    "Energy":       r"\b(GW|renewable|solar|wind|electricity|PV|power)\b",
    "Climate":      r"\b(CO2|emission|Paris Agreement|GHG)\b",
    "Construction": r"\b(construction|housing|dwelling|building permit)\b",
    "Labour":       r"\b(unemployment|employment|wage)\b",
    "Trade":        r"\b(export|import|sanction|tariff)\b",
    "Finance":      r"\b(debt|budget deficit|fiscal)\b",
    "Economic Recovery": r"\b(recovery|rebound|stimulus|bounce\s?back|expansion|growth momentum)\b",
    "Policy": r"\b(policy|regulation|directive|legislation|law|strategy|framework|ordinance)\b",
    "Work Models": r"\b(remote work|telework|hybrid work|flexible working|gig economy|home office|four-day week)\b",
    "Industry": r"\b(industry|industrial|manufacturing|factory|plant|production|industrial output|processing sector)\b",

    # ─────── new topics ───────
    # broad macro turnarounds, stimulus packages, post-crisis bounce-backs
    # "Economic Recovery": r"\b(recovery|rebound|stimulus|bounce\s?back|expansion|growth momentum)\b",

    # generic references to rules, strategies and official guidance
    # "Policy": r"\b(policy|regulation|directive|legislation|law|strategy|framework|ordinance)\b",

    # how and where people work
    # "Work Models": r"\b(remote work|telework|hybrid work|flexible working|gig economy|home office|four-day week)\b",

    # industrial output and capacity
    # "Industry": r"\b(industry|industrial|manufacturing|factory|plant|production|industrial output|processing sector)\b",
}

def classify_text():
    fp_in  = OUT / "sentences_clean.parquet"
    fp_out = OUT / "sentences_topic.parquet"
    if not fp_in.exists():
        print("⚠️  run 'clean' first"); return
    df = pd.read_parquet(fp_in)
    def label(row):
        for topic, pat in KEYWORDS.items():
            if re2.search(pat, row, flags=re2.I):
                return topic
        return "Other"
    df["topic"] = df["text"].map(label)
    df.to_parquet(fp_out)
    print("✅ classified →", fp_out.name)

# ---------------------------------------------------------------------------
# 4 · TIME-BIN TAGGING
# ---------------------------------------------------------------------------
def tag_timeline():
    fp_in  = OUT / "sentences_topic.parquet"
    fp_out = OUT / "sentences_time.parquet"
    if not fp_in.exists():
        print("⚠️  run 'classify' first"); return
    df = pd.read_parquet(fp_in)

    def time_bin(sentence: str) -> str:
        yrs = re.findall(r'\b(19|20)\d{2}\b', sentence)
        if yrs:
            y = max(map(int, yrs))
            if y <= 2022: return "Past"
            if y in (2023, 2024): return "Present"
            return "Future"
        if re.search(r'\bwill\b|\btarget\b|\bby 20\d{2}\b', sentence, re.I):
            return "Future"
        if re.search(r'\bhas\b|\bis\b', sentence, re.I):
            return "Present"
        return "Past"

    df["time_bin"] = df["text"].map(time_bin)
    df.to_parquet(fp_out)
    print("✅ timeline tags →", fp_out.name)

# load TEXT lazily when story step runs
TEXT = None

# ---------------------------------------------------------------------------
# 5 · Llama-cpp SETUP + make_story()
# ---------------------------------------------------------------------------
def load_llm():
    from llama_cpp import Llama
    return Llama(
        model_path="models/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        n_ctx=8192,
        n_gpu_layers=10,
        n_threads=8,
        verbose=False
    )

LLM = None  # will be initialised on first call

def make_story(topic: str) -> str:
    """
    Return a Past-Present-Future story on *topic* plus a reference list
    (file name + page) built from the same snippets fed to the LLM.
    """
    global LLM, TEXT
    if LLM is None:
        LLM = load_llm()
    if TEXT is None:
        TEXT = pd.read_parquet(OUT / "sentences_time.parquet")

    sub     = TEXT[TEXT.topic == topic]
    buckets = {"Past": [], "Present": [], "Future": []}
    refs    = set()                       # ← stash citation strings here

    for t in buckets:
        rows = sub[sub.time_bin == t].nlargest(3, "page")
        lines = []
        for _, r in rows.iterrows():
            cite  = f"{r.file} p.{r.page}"
            lines.append(f"{r.text} ({cite})")  # inline citation
            refs.add(cite)
        buckets[t] = lines or ["**No data found**"]

    prompt = f"""
You are an economic analyst. Write a concise story on **{topic}**
in three paragraphs (Past, Present, Future). Quote numbers from the
snippets. ≤120 words per paragraph. Return plain text.

Snippets:
Past: { ' | '.join(buckets['Past']) }
Present: { ' | '.join(buckets['Present']) }
Future: { ' | '.join(buckets['Future']) }
""".strip()

    rsp = LLM(
        prompt,
        max_tokens=380,
        temperature=0.2,
        top_p=0.9,
        stop=["</s>", "Snippets:"]
    )
    story = rsp["choices"][0]["text"].strip()

    # ---------- tack on a tidy reference list ----------
    if refs:
        story += "\n\n**References**\n" + "\n".join(f"– {c}" for c in sorted(refs))

    return story

# ---------------------------------------------------------------------------
# 6 · WRITE STORIES
# ---------------------------------------------------------------------------
def write_stories():
    global TEXT
    if TEXT is None:
        TEXT = pd.read_parquet(OUT / "sentences_time.parquet")

    topics = TEXT.topic.unique()
    if len(topics) == 0:
        print("⚠️  No topics found – run previous steps first"); return

    for topic in topics:
        print(">> generating", topic)
        story = make_story(topic)
        print("   ✔ got", len(story), "chars")
        (OUT / f"story_{topic}.txt").write_text(story, encoding="utf-8")

    print(f"✅ {len(topics)} stories written to {OUT.resolve()}\\")


def compare_topics(topic_a: str, topic_b: str) -> str:
    """
    If pages exist that link *topic_a* and *topic_b*, return a connected
    story + reference list. Otherwise return 'Nothing to match'.
    """
    global LLM, TEXT
    if LLM is None:
        LLM = load_llm()
    if TEXT is None:
        TEXT = pd.read_parquet(OUT / "sentences_time.parquet")

    overlaps = overlap_snippets(topic_a, topic_b, TEXT)

    # 1. No connection? -------------
    if not overlaps:
        return f"Nothing to match between **{topic_a}** and **{topic_b}**."

    # 2. Build prompt ---------------
    refs = set()
    joined = []
    for item in overlaps[:5]:                # pass at most 5 pages to keep prompt short
        cite = f"{item['file']} p.{item['page']}"
        refs.add(cite)
        for line in item["snippets"]:
            joined.append(f"{line} ({cite})")

    prompt = f"""
You are a policy analyst.  Write one cohesive paragraph (≤180 words)
that explains how **{topic_a}** and **{topic_b}** are connected in the
report.  Base yourself only on the snippets; quote at least one number.
Return plain text.

Snippets:
{ " | ".join(joined) }
""".strip()

    rsp = LLM(prompt, max_tokens=220, temperature=0.25)
    story = rsp["choices"][0]["text"].strip()

    story += "\n\n**References**\n" + "\n".join(f"– {r}" for r in sorted(refs))
    return story

# >>> cohesive paragraph or “Nothing to match …”


# ---------------------------------------------------------------------------
#  CLI DISPATCHER
# ---------------------------------------------------------------------------
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd in ("extract", "all"):   extract_text()
    if cmd in ("clean",   "all"):   clean_text()
    if cmd in ("classify","all"):   classify_text()
    if cmd in ("timeline","all"):   tag_timeline()
    if cmd in ("story",   "all"):   write_stories()

    if cmd not in ("extract","clean","classify","timeline","story","all"):
        print("Usage: python storylab.py "
              "[extract|clean|classify|timeline|story|all]")

if __name__ == "__main__":
    main()
