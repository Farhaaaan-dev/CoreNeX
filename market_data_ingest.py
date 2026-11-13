"""
CoreNex market-data ingestion pipeline.

Collects public, downloadable job-market and technology-trend data, normalizes it
to a monthly skill-demand table, and records source provenance.

Run:
    python market_data_ingest.py

The pipeline never invents observations. Sources that require credentials,
paid access, or scraping that is not permitted are recorded as skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
import requests
import ahocorasick

PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DIR = PROJECT_ROOT / "market_data" / "raw"
PROC_DIR = PROJECT_ROOT / "market_data" / "processed"
CACHE_DIR = PROJECT_ROOT / "market_data" / "cache"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROC_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

RUN_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")
PRIMARY_MONTHS = pd.period_range("2026-01", "2026-10", freq="M")

PIPELINE_VERSION = "2.0.0"
STATE_VERSION = 2
STATE_PATH = PROC_DIR / "ingestion_state.json"
MANIFEST_PATH = PROC_DIR / "collection_manifest.json"
REGISTRY_PATH = PROC_DIR / "source_registry.json"
VOCAB_CACHE_PATH = PROC_DIR / "vocabulary_cache.json"
GITHUB_CACHE_PATH = CACHE_DIR / "github_activity.json"
BLS_CACHE_PATH = CACHE_DIR / "bls_jolts.json"

# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------
# Every entry is explicit about access method and licence. `status` is updated
# after the adapter runs. No source is presented as connected unless it was read.
SOURCE_REGISTRY: List[Dict] = [
    {
        "id": "fliar_2026",
        "name": "Fliar Research — Job Postings 2026 (India & US)",
        "publisher": "Fliar Research",
        "url": "https://huggingface.co/datasets/fliarbi/job-postings-2026",
        "file_url": "https://huggingface.co/datasets/fliarbi/job-postings-2026/resolve/main/job_postings_2026_sample.csv",
        "license": "CC BY-NC 4.0",
        "access_method": "Public Hugging Face CSV download",
        "role": "primary_historical",
        "status": "pending",
        "notes": "6% sample (100,009 of 1,654,294 postings), Jan-Jun 2026, US/India, dated and skill-labelled.",
    },
    {
        "id": "nextgig_2026_06",
        "name": "NextGig — Multi-ATS Job Postings Snapshot (June 2026)",
        "publisher": "NextGig",
        "url": "https://huggingface.co/datasets/NextGig-Rocks/global-job-postings-multi-ats",
        "file_url": "https://huggingface.co/datasets/NextGig-Rocks/global-job-postings-multi-ats/resolve/main/nextgig_jobs_2026-06.parquet",
        "license": "CC BY 4.0",
        "access_method": "Public Hugging Face parquet download",
        "role": "primary_snapshot",
        "status": "pending",
        "notes": "112,816 postings, 23 ATS systems, structured skills_required; date_posted sparse.",
    },
    {
        "id": "joa_2026_10",
        "name": "Job Opportunities API — Employer-direct postings (Oct 2026)",
        "publisher": "Job Opportunities API",
        "url": "https://huggingface.co/datasets/JobOpportunitiesAPI/joa-employer-direct-job-postings-2026-10",
        "file_url": "https://huggingface.co/datasets/JobOpportunitiesAPI/joa-employer-direct-job-postings-2026-10/resolve/main/joa_hf_25k.jsonl",
        "license": "CC BY 4.0",
        "access_method": "Public Hugging Face JSONL download",
        "role": "primary_historical",
        "status": "pending",
        "notes": "25,000 employer-direct postings; first_seen Jul-Aug 2026; descriptions used for skill extraction.",
    },
    {
        "id": "minmaxxxer_2026_10",
        "name": "MinMaxxxer — Job postings with salaries (Oct 2026)",
        "publisher": "MinMaxxxer",
        "url": "https://huggingface.co/datasets/minmaxxxer/job-postings-with-salaries-2026-10",
        "file_url": "https://huggingface.co/datasets/minmaxxxer/job-postings-with-salaries-2026-10/resolve/main/job_postings_with_salaries_2026_10.csv",
        "license": "Research/analysis use; posting text remains with employers",
        "access_method": "Public Hugging Face CSV download",
        "role": "primary_historical",
        "status": "pending",
        "notes": "10,000 postings from 10 ATS systems, posted 2026-09-09 to 2026-10-09; descriptions used for skill extraction.",
    },
    {
        "id": "indeed_sample_2026",
        "name": "Indeed Jobs sample (2026)",
        "publisher": "Fact.Den / Apify sample",
        "url": "https://huggingface.co/datasets/fact-den/indeed-job-postings-2026",
        "file_url": "https://huggingface.co/datasets/fact-den/indeed-job-postings-2026/resolve/main/jobs/jobs.csv",
        "license": "Other — public research sample",
        "access_method": "Public Hugging Face CSV download",
        "role": "corroborating_sample",
        "status": "pending",
        "notes": "1,000 Indeed postings with descriptions and dates; sample, not a live Indeed feed.",
    },
    {
        "id": "datamatastudios_2026_11",
        "name": "Datamata Skill Demand Index (11 Nov 2026)",
        "publisher": "Datamata Studios",
        "url": "https://huggingface.co/datasets/datamatastudios/skill-demand-index",
        "file_url": "https://huggingface.co/datasets/datamatastudios/skill-demand-index/resolve/main/skill-demand-index.csv",
        "license": "CC BY 4.0",
        "access_method": "Public Hugging Face CSV download",
        "role": "current_snapshot",
        "status": "pending",
        "notes": "Daily tech-listing skill shares across data, engineering, product, DevOps, security and AI; snapshot 2026-11-11.",
    },
    {
        "id": "yash_2026_overall",
        "name": "Most in-demand skills 2026 (360k postings)",
        "publisher": "Yash Raj",
        "url": "https://huggingface.co/datasets/yash2111/most-in-demand-skills-2026",
        "file_url": "https://huggingface.co/datasets/yash2111/most-in-demand-skills-2026/resolve/main/skills-2026-overall.csv",
        "license": "CC BY 4.0",
        "access_method": "Public Hugging Face CSV download",
        "role": "corroborating_aggregate",
        "status": "pending",
        "notes": "Top 250 skills from 360,336 postings, Dec 2025-Jun 2026; aggregate, not monthly.",
    },
    {
        "id": "github_trends",
        "name": "GitHub repository creation trends",
        "publisher": "GitHub REST API",
        "url": "https://api.github.com/search/repositories",
        "file_url": "https://api.github.com/search/repositories",
        "license": "GitHub API terms",
        "access_method": "Public REST API, unauthenticated (10 requests/min)",
        "role": "technology_activity",
        "status": "pending",
        "notes": "Repository counts created Jan-Nov 2026 for selected technologies; auxiliary developer-activity signal, not job demand.",
    },
    {
        "id": "bls_jolts",
        "name": "BLS JOLTS job openings",
        "publisher": "U.S. Bureau of Labor Statistics",
        "url": "https://www.bls.gov/jlt/",
        "file_url": "https://api.bls.gov/publicAPI/v1/timeseries/data/",
        "license": "Public domain / BLS terms",
        "access_method": "Public BLS API v1",
        "role": "macro_context",
        "status": "pending",
        "notes": "Total nonfarm job openings, seasonally adjusted; macro context only, not a skill-level series.",
    },
    {
        "id": "google_trends",
        "name": "Google Trends",
        "publisher": "Google",
        "url": "https://trends.google.com/",
        "file_url": "",
        "license": "Google Trends terms",
        "access_method": "Official Trends API is alpha; no public API key configured",
        "role": "optional_context",
        "status": "skipped",
        "notes": "Not connected: Google's official Trends API is access-by-application alpha; pytrends is archived. No unofficial scraping is performed.",
    },
    {
        "id": "linkedin",
        "name": "LinkedIn job-market insights",
        "publisher": "LinkedIn",
        "url": "https://www.linkedin.com/",
        "file_url": "",
        "license": "LinkedIn Terms of Service",
        "access_method": "No public job-postings API; scraping not permitted",
        "role": "optional_context",
        "status": "skipped",
        "notes": "Not connected: no public API or permitted bulk access. No scraping or fabricated LinkedIn data.",
    },
    {
        "id": "indeed_live",
        "name": "Indeed live job postings",
        "publisher": "Indeed",
        "url": "https://www.indeed.com/",
        "file_url": "",
        "license": "Indeed Terms of Service",
        "access_method": "No public API; scraping not permitted",
        "role": "optional_context",
        "status": "skipped",
        "notes": "Not connected: no public API or permitted bulk access. The public 2026 sample above is used only as a labelled corroborating sample.",
    },
    {
        "id": "kaggle_global_jobs",
        "name": "Kaggle global job-market postings",
        "publisher": "Kaggle",
        "url": "https://www.kaggle.com/",
        "file_url": "",
        "license": "Dataset-specific",
        "access_method": "Kaggle API credentials not configured",
        "role": "optional_context",
        "status": "skipped",
        "notes": "Not connected: Kaggle API credentials are not configured; no dataset is downloaded anonymously.",
    },
]

SOURCE_BY_ID = {s["id"]: s for s in SOURCE_REGISTRY}

# ---------------------------------------------------------------------------
# Cache / state / progress helpers
# ---------------------------------------------------------------------------
# Cached API responses are stored under market_data/cache with an expiry so a
# resume or a rerun does not re-hit rate-limited endpoints. Pipeline checkpoints
# let an interrupted run continue without redoing completed work.

DEFAULT_CACHE_TTL_HOURS = 24.0
DEFAULT_OUTPUT_VALIDATION = True


class Progress:
    """Simple stage/elapsed logger so a long ingestion run is observable."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.start = time.time()
        self.stage = ""
        self.stage_start = self.start
        print(f"[{label}] start {RUN_TS}", flush=True)

    def step(self, name: str, detail: str = "") -> None:
        now = time.time()
        prev = self.stage
        self.stage = name
        self.stage_start = now
        suffix = f" ({detail})" if detail else ""
        print(f"  +{now - self.start:7.1f}s  {name}{suffix}"
              + (f"  [prev {prev} took {now - self.stage_start:.1f}s]" if prev else ""),
              flush=True)

    def done(self) -> None:
        print(f"[{self.label}] done in {time.time() - self.start:.1f}s", flush=True)


def _json_cache_load(path: Path, max_age_hours: float) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        age_h = (time.time() - path.stat().st_mtime) / 3600.0
        if age_h > max_age_hours:
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        data["_cache_age_hours"] = round(age_h, 3)
        return data
    except Exception:  # noqa: BLE001
        return None


def _json_cache_save(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _state_load() -> dict:
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                st = json.load(f)
            if isinstance(st, dict) and st.get("state_version") == STATE_VERSION:
                return st
        except Exception:  # noqa: BLE001
            pass
    return {"state_version": STATE_VERSION, "pipeline_version": PIPELINE_VERSION,
            "completed_steps": [], "started_at": RUN_TS, "sources": {}}


def _state_save(state: dict) -> None:
    state["pipeline_version"] = PIPELINE_VERSION
    state["state_version"] = STATE_VERSION
    state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _json_cache_save(STATE_PATH, state)


def _vocab_signature() -> dict:
    """Fingerprint of the inputs that determine the skill vocabulary.

    The vocabulary is rebuilt only when one of the raw corpora it is derived
    from changes, so a resume skips a costly rebuild when nothing moved.
    """
    sig = {}
    for fname in [
        "fliar_job_postings_2026_sample.csv",
        "nextgig_jobs_2026_06.parquet",
        "yash_skills_2026_overall.csv",
        "datamatastudios_skill_demand_index.csv",
    ]:
        p = RAW_DIR / fname
        if p.exists():
            st = p.stat()
            sig[fname] = {"bytes": st.st_size, "mtime": int(st.st_mtime)}
    p = PROJECT_ROOT / "weekly_skill_demand.csv"
    if p.exists():
        st = p.stat()
        sig["weekly_skill_demand.csv"] = {"bytes": st.st_size, "mtime": int(st.st_mtime)}
    return sig


def _build_automaton(counts: Dict[str, int], existing: Set[str]) -> ahocorasick.Automaton:
    top = [s for s, _ in Counter(counts).most_common(650) if len(s) >= 2]
    vocab = sorted((set(top) | existing))
    vocab = [s for s in vocab if s and s not in BLOCK_REGEX]
    automaton = ahocorasick.Automaton()
    for s in vocab:
        automaton.add_word(s, s)
    automaton.make_automaton()
    return automaton


def _validate_csv(path: Path, required: Sequence[str], min_rows: int = 1) -> Tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return False, f"unreadable: {type(exc).__name__}"
    if df.empty or len(df) < min_rows:
        return False, f"insufficient rows ({len(df)})"
    missing = [c for c in required if c not in df.columns]
    if missing:
        return False, f"missing columns {missing}"
    return True, f"{len(df)} rows"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, out: Path, min_bytes: int = 1000) -> Tuple[bool, str]:
    if out.exists() and out.stat().st_size >= min_bytes:
        return True, "cached"
    try:
        r = requests.get(url, timeout=300, stream=True)
        r.raise_for_status()
        tmp = out.with_suffix(out.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        tmp.replace(out)
        return True, "downloaded"
    except Exception as exc:  # noqa: BLE001
        if out.exists() and out.stat().st_size >= min_bytes:
            return True, "cached_after_error"
        return False, f"{type(exc).__name__}: {exc}"


def norm_skill(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return ""
    s = str(raw).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "powerbi": "power bi",
    "node": "node.js",
    "nodejs": "node.js",
    "reactjs": "react.js",
    "vuejs": "vue.js",
    "angularjs": "angular.js",
    "golang": "go",
    "mssql": "sql server",
    "google cloud platform": "gcp",
    "amazon web services": "aws",
    "microsoft azure": "azure",
    ".net": ".net",
    "dotnet": ".net",
    "genai": "generative ai",
    "llms": "llm",
    "ci cd": "ci/cd",
    "c++": "c++",
    "c#": "c#",
}

BLOCK_REGEX = {"go", "c", "it", "hr", "pr"}

# Generic workplace skills that are not the focus of CoreNex's technology taxonomy.
GENERIC_TECH_BLOCKLIST = {
    "communication", "communication skills", "leadership", "training", "insurance",
    "operations", "organization", "compliance", "sales", "safety", "documentation",
    "reporting", "planning", "delivery", "travel", "driving", "research", "healthcare",
    "finance", "attention to detail", "teamwork", "collaboration", "problem solving",
    "customer service", "project", "management", "product", "business", "analysis",
    "analyst", "support", "stakeholder", "stakeholder mgmt", "soft skill",
}

# Technology / emerging-technology taxonomy used to keep the forecast universe
# focused on CoreNex's labour-market scope. This is a filter, not a data source.
CURATED_TECH_SKILLS = """
python sql aws azure gcp machine learning deep learning data analysis data engineering
data science analytics business intelligence power bi tableau looker qlik metabase superset
redash excel google sheets spreadsheets etl elt data pipeline data warehouse data lake
snowflake databricks bigquery redshift synapse fabric postgres postgresql mysql sql server
sqlserver oracle mongodb mongo redis cassandra dynamodb elasticsearch solr neo4j
hadoop hive presto trino spark pyspark apache spark apache kafka kafka streams flink beam nifi
airflow dagster prefect luigi dbt apache airflow apache nifi
javascript typescript react react.js next.js nextjs vue vue.js angular angular.js svelte
node.js nodejs express django flask fastapi spring spring boot .net dotnet ruby on rails
laravel php java kotlin swift dart flutter react native android ios html css sass tailwind
bootstrap jquery redux webpack vite babel npm yarn pnpm git github gitlab bitbucket jenkins
gitlab ci github actions circleci travis ci argo cd argocd terraform ansible chef puppet
docker kubernetes k8s openshift rancher helm istio prometheus grafana datadog new relic splunk
cloudformation serverless lambda fargate ec2 s3 rds ecs eks cloudfront route 53
linux ubuntu debian centos red hat bash shell powershell networking tcp ip dns vpn firewall
security cybersecurity siem soc iso 27001 soc 2 pci dss gdpr hipaa compliance risk
pytorch tensorflow keras scikit-learn sklearn xgboost lightgbm catboost optuna ray onnx
tensorrt openvino hugging face transformers llm llms genai generative ai rag langchain
llamaindex pinecone weaviate milvus qdrant chroma faiss pgvector vector database
mcp agentic ai ai agents prompt engineering nlp computer vision opencv spacy nltk bert gpt
mlops feature store model deployment model monitoring sagemaker vertex ai azure openai
bedrock anthropic openai claude gemini mistral cohere vllm
power platform power apps power automate sharepoint microsoft office excel vba
salesforce hubspot sap oracle erp workday servicenow jira confluence agile scrum kanban
safe waterfall trello asana monday.com notion
tableau desktop tableau server qlikview qlik sense microstrategy cognos
data visualization dashboard reporting kpi metrics statistics forecasting time series
regression classification clustering a/b testing experimentation hypothesis testing
statistics spss stata sas matlab julia scala r perl ruby groovy cobol fortran
technical writing documentation communication stakeholder management project management
product management product owner business analysis requirements gathering
"""


def canonical_skill(raw: object) -> str:
    s = norm_skill(raw)
    if not s:
        return ""
    s = ALIASES.get(s, s)
    return s


def split_skill_text(value: object) -> List[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value if str(x).strip()]
    s = str(value).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x).strip()]
        except Exception:  # noqa: BLE001
            pass
    return [x for x in re.split(r"[|,;]", s) if x.strip()]


def parse_skill_set(value: object) -> Set[str]:
    out = set()
    for raw in split_skill_text(value):
        s = canonical_skill(raw)
        if s:
            out.add(s)
    return out


def safe_text(value: object, limit: int = 12000) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return str(value)[:limit]


# ---------------------------------------------------------------------------
# Vocabulary / regex extraction
# ---------------------------------------------------------------------------

def build_vocabulary(use_cache: bool = True) -> Tuple[Dict[str, int], ahocorasick.Automaton, Dict]:
    sig = _vocab_signature()
    if use_cache and VOCAB_CACHE_PATH.exists():
        try:
            with open(VOCAB_CACHE_PATH, encoding="utf-8") as f:
                blob = json.load(f)
            if blob.get("signature") == sig and isinstance(blob.get("counts"), dict):
                automaton = _build_automaton(blob["counts"], set(blob.get("existing", [])))
                return blob["counts"], automaton, {"status": "cached", "detail": "vocabulary reused"}
        except Exception:  # noqa: BLE001
            pass

    counts: Counter = Counter()

    # Fliar
    p = RAW_DIR / "fliar_job_postings_2026_sample.csv"
    if p.exists():
        df = pd.read_csv(p, usecols=["skills"], low_memory=False)
        for v in df["skills"].dropna():
            counts.update(parse_skill_set(v))

    # NextGig
    p = RAW_DIR / "nextgig_jobs_2026_06.parquet"
    if p.exists():
        df = pd.read_parquet(p, columns=["skills_required"])
        for v in df["skills_required"].dropna():
            counts.update(parse_skill_set(v))

    # Yash
    p = RAW_DIR / "yash_skills_2026_overall.csv"
    if p.exists():
        df = pd.read_csv(p)
        for v in df["skill"].dropna():
            s = canonical_skill(v)
            if s:
                counts[s] += 1

    # Datamata
    p = RAW_DIR / "datamatastudios_skill_demand_index.csv"
    if p.exists():
        df = pd.read_csv(p)
        for v in df["skill"].dropna():
            s = canonical_skill(v)
            if s:
                counts[s] += 1

    # Existing CoreNex vocabulary
    existing: Set[str] = set()
    p = PROJECT_ROOT / "weekly_skill_demand.csv"
    if p.exists():
        df = pd.read_csv(p, usecols=["skill"])
        for v in df["skill"].dropna().unique():
            s = canonical_skill(v)
            if s:
                counts.setdefault(s, 0)
                existing.add(s)

    # Keep a manageable vocabulary for description extraction. The full list is
    # retained in the discovery table; only the most common terms are matched.
    top = [s for s, _ in counts.most_common(650) if len(s) >= 2]
    vocab = sorted(set(top) | existing)
    vocab = [s for s in vocab if s and s not in BLOCK_REGEX]

    # Aho-Corasick scans each document once, which is essential for the large
    # JOA/MinMaxxxer description corpora.
    automaton = _build_automaton(dict(counts), existing)
    if use_cache:
        try:
            _json_cache_save(VOCAB_CACHE_PATH, {
                "signature": sig,
                "counts": dict(counts),
                "existing": sorted(existing),
            })
        except Exception:  # noqa: BLE001
            pass
    return dict(counts), automaton, {"status": "rebuilt", "detail": "vocabulary rebuilt"}


def extract_skills(text: str, extractor: ahocorasick.Automaton) -> Set[str]:
    if not text:
        return set()
    # Descriptions can be long; the first 6k characters contain the overwhelming
    # majority of stated requirements while keeping ingestion tractable.
    t = text[:6000].lower()
    out: Set[str] = set()
    for end, term in extractor.iter(t):
        start = end - len(term) + 1
        if start > 0 and t[start - 1].isalnum():
            continue
        if end + 1 < len(t) and t[end + 1].isalnum():
            continue
        out.add(canonical_skill(term))
    return out


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------

def load_fliar(patterns: Dict[str, re.Pattern]) -> Tuple[pd.DataFrame, Dict]:
    p = RAW_DIR / "fliar_job_postings_2026_sample.csv"
    ok, detail = download(SOURCE_BY_ID["fliar_2026"]["file_url"], p)
    if not ok:
        return pd.DataFrame(), {"status": "failed", "detail": detail}
    df = pd.read_csv(p, usecols=["posting_id", "posted_date", "title", "company", "country", "category", "skills"], low_memory=False)
    df["month"] = pd.to_datetime(df["posted_date"], errors="coerce").dt.to_period("M").astype(str)
    df = df.dropna(subset=["month"])
    df["skills_set"] = df["skills"].apply(parse_skill_set)
    rows = []
    for month, grp in df.groupby("month"):
        total = len(grp)
        c: Counter = Counter()
        for ss in grp["skills_set"]:
            c.update(ss)
        for skill, n in c.items():
            rows.append({
                "month": month, "skill": skill, "source_id": "fliar_2026",
                "postings_with_skill": int(n), "source_postings": int(total),
                "demand_share_pct": float(n) / float(total) * 100.0 if total else 0.0,
                "extraction_method": "provided_skills",
            })
    out = pd.DataFrame(rows)
    return out, {
        "status": "ok", "rows": int(len(df)), "months": sorted(df["month"].unique().tolist()),
        "date_min": str(pd.to_datetime(df["posted_date"], errors="coerce").min()),
        "date_max": str(pd.to_datetime(df["posted_date"], errors="coerce").max()),
        "detail": detail,
    }


def load_nextgig(patterns: Dict[str, re.Pattern]) -> Tuple[pd.DataFrame, Dict]:
    p = RAW_DIR / "nextgig_jobs_2026_06.parquet"
    ok, detail = download(SOURCE_BY_ID["nextgig_2026_06"]["file_url"], p)
    if not ok:
        return pd.DataFrame(), {"status": "failed", "detail": detail}
    df = pd.read_parquet(p, columns=["title", "company_name", "skills_required", "date_posted"])
    df["skills_set"] = df["skills_required"].apply(parse_skill_set)
    total = len(df)
    c: Counter = Counter()
    for ss in df["skills_set"]:
        c.update(ss)
    rows = []
    for skill, n in c.items():
        rows.append({
            "month": "2026-06", "skill": skill, "source_id": "nextgig_2026_06",
            "postings_with_skill": int(n), "source_postings": int(total),
            "demand_share_pct": float(n) / float(total) * 100.0 if total else 0.0,
            "extraction_method": "provided_skills_snapshot",
        })
    dates = pd.to_datetime(df["date_posted"], errors="coerce", format="mixed")
    return pd.DataFrame(rows), {
        "status": "ok", "rows": int(total), "months": ["2026-06"],
        "date_min": str(dates.min()), "date_max": str(dates.max()),
        "detail": detail,
    }


def load_joa(patterns: Dict[str, re.Pattern]) -> Tuple[pd.DataFrame, Dict]:
    p = RAW_DIR / "joa_employer_direct_2026_10.jsonl"
    ok, detail = download(SOURCE_BY_ID["joa_2026_10"]["file_url"], p)
    if not ok:
        return pd.DataFrame(), {"status": "failed", "detail": detail}
    rows = []
    month_totals: Counter = Counter()
    month_counts: Dict[str, Counter] = defaultdict(Counter)
    n = 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                j = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            n += 1
            d = pd.to_datetime(j.get("first_seen_at"), errors="coerce")
            if pd.isna(d):
                continue
            month = d.to_period("M").strftime("%Y-%m")
            month_totals[month] += 1
            text = safe_text(j.get("title")) + "\n" + safe_text(j.get("description"))
            for s in extract_skills(text, patterns):
                month_counts[month][s] += 1
    for month, c in month_counts.items():
        total = month_totals[month]
        for s, cnt in c.items():
            rows.append({
                "month": month, "skill": s, "source_id": "joa_2026_10",
                "postings_with_skill": int(cnt), "source_postings": int(total),
                "demand_share_pct": float(cnt) / float(total) * 100.0 if total else 0.0,
                "extraction_method": "description_regex",
            })
    return pd.DataFrame(rows), {"status": "ok", "rows": int(n), "months": sorted(month_totals), "detail": detail}


def load_minmaxxxer(patterns: Dict[str, re.Pattern]) -> Tuple[pd.DataFrame, Dict]:
    p = RAW_DIR / "minmaxxxer_job_postings_2026_10.csv"
    ok, detail = download(SOURCE_BY_ID["minmaxxxer_2026_10"]["file_url"], p)
    if not ok:
        return pd.DataFrame(), {"status": "failed", "detail": detail}
    df = pd.read_csv(p, usecols=["job_id", "title", "posted_at", "description"], low_memory=False)
    df["month"] = pd.to_datetime(df["posted_at"], errors="coerce", utc=True).dt.tz_convert(None).dt.to_period("M").astype(str)
    df = df.dropna(subset=["month"])
    month_totals = df.groupby("month").size().to_dict()
    rows = []
    for month, grp in df.groupby("month"):
        c: Counter = Counter()
        for text in (grp["title"].fillna("").astype(str) + "\n" + grp["description"].fillna("").astype(str)):
            c.update(extract_skills(text, patterns))
        total = int(month_totals[month])
        for s, cnt in c.items():
            rows.append({
                "month": month, "skill": s, "source_id": "minmaxxxer_2026_10",
                "postings_with_skill": int(cnt), "source_postings": total,
                "demand_share_pct": float(cnt) / float(total) * 100.0 if total else 0.0,
                "extraction_method": "description_regex",
            })
    return pd.DataFrame(rows), {"status": "ok", "rows": int(len(df)), "months": sorted(df["month"].unique().tolist()), "detail": detail}


def load_indeed_sample(patterns: Dict[str, re.Pattern]) -> Tuple[pd.DataFrame, Dict]:
    p = RAW_DIR / "indeed_jobs_sample_2026.csv"
    ok, detail = download(SOURCE_BY_ID["indeed_sample_2026"]["file_url"], p)
    if not ok:
        return pd.DataFrame(), {"status": "failed", "detail": detail}
    df = pd.read_csv(p, usecols=["jobKey", "title", "datePosted", "description"], low_memory=False)
    df["month"] = pd.to_datetime(df["datePosted"], errors="coerce").dt.to_period("M").astype(str)
    df = df.dropna(subset=["month"])
    # The public sample contains some older postings; use only its 2026 rows.
    df = df[(df["month"] >= "2026-01") & (df["month"] <= "2026-12")]
    month_totals = df.groupby("month").size().to_dict()
    rows = []
    for month, grp in df.groupby("month"):
        c: Counter = Counter()
        for text in (grp["title"].fillna("").astype(str) + "\n" + grp["description"].fillna("").astype(str)):
            c.update(extract_skills(text, patterns))
        total = int(month_totals[month])
        for s, cnt in c.items():
            rows.append({
                "month": month, "skill": s, "source_id": "indeed_sample_2026",
                "postings_with_skill": int(cnt), "source_postings": total,
                "demand_share_pct": float(cnt) / float(total) * 100.0 if total else 0.0,
                "extraction_method": "description_regex",
            })
    return pd.DataFrame(rows), {"status": "ok", "rows": int(len(df)), "months": sorted(df["month"].unique().tolist()), "detail": detail}


def load_datamatastudios(patterns: Dict[str, re.Pattern]) -> Tuple[pd.DataFrame, Dict]:
    p = RAW_DIR / "datamatastudios_skill_demand_index.csv"
    ok, detail = download(SOURCE_BY_ID["datamatastudios_2026_11"]["file_url"], p)
    if not ok:
        return pd.DataFrame(), {"status": "failed", "detail": detail}
    df = pd.read_csv(p)
    df["skill_norm"] = df["skill"].apply(canonical_skill)
    cat_totals = df.groupby("category")["total_listings"].max()
    total = float(cat_totals.sum())
    rows = []
    for skill, grp in df.groupby("skill_norm"):
        if not skill:
            continue
        listings = float(grp["listing_count"].sum())
        required = float(grp["required_count"].sum())
        rows.append({
            "month": "2026-11", "skill": skill, "source_id": "datamatastudios_2026_11",
            "postings_with_skill": int(listings), "source_postings": int(total),
            "demand_share_pct": listings / total * 100.0 if total else 0.0,
            "required_share_pct": required / total * 100.0 if total else 0.0,
            "category": "|".join(sorted(grp["category"].dropna().astype(str).unique())),
            "extraction_method": "provided_index",
        })
    return pd.DataFrame(rows), {
        "status": "ok", "rows": int(len(df)), "months": ["2026-11"],
        "snapshot_date": str(pd.to_datetime(df["snapshot_date"], errors="coerce").max()),
        "detail": detail,
    }


def load_yash() -> Tuple[pd.DataFrame, Dict]:
    p = RAW_DIR / "yash_skills_2026_overall.csv"
    ok, detail = download(SOURCE_BY_ID["yash_2026_overall"]["file_url"], p)
    if not ok:
        return pd.DataFrame(), {"status": "failed", "detail": detail}
    df = pd.read_csv(p)
    df["skill_norm"] = df["skill"].apply(canonical_skill)
    total = 360336.0
    rows = []
    for _, r in df.iterrows():
        if not r["skill_norm"]:
            continue
        rows.append({
            "month": "2026-06", "skill": r["skill_norm"], "source_id": "yash_2026_overall",
            "postings_with_skill": int(r["postings_with_skill"]), "source_postings": int(total),
            "demand_share_pct": float(r["pct_of_all_postings"]),
            "extraction_method": "provided_aggregate",
        })
    return pd.DataFrame(rows), {"status": "ok", "rows": int(len(df)), "months": ["2026-06"], "detail": detail}


# ---------------------------------------------------------------------------
# Auxiliary sources
# ---------------------------------------------------------------------------

def _github_from_cache(cache: dict) -> pd.DataFrame:
    rows = cache.get("rows") or []
    if not isinstance(rows, list):
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    if not out.empty:
        out.to_csv(PROC_DIR / "github_activity.csv", index=False)
    return out


def _bls_from_cache(cache: dict) -> pd.DataFrame:
    rows = cache.get("data") or []
    if not isinstance(rows, list):
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    if not out.empty:
        out.to_csv(PROC_DIR / "bls_jolts.csv", index=False)
    return out


def load_github(cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS,
                use_cache: bool = True) -> Tuple[pd.DataFrame, Dict]:
    if use_cache:
        cached = _json_cache_load(GITHUB_CACHE_PATH, cache_ttl_hours)
        if cached is not None:
            df = _github_from_cache(cached)
            return df, {"status": "ok", "rows": int(len(df)), "detail": "cache",
                        "cache_age_hours": cached.get("_cache_age_hours")}
    queries = {
        "python": "language:Python",
        "javascript": "language:JavaScript",
        "typescript": "language:TypeScript",
        "java": "language:Java",
        "go": "language:Go",
        "rust": "language:Rust",
        "c++": "language:C++",
        "c#": "language:CSharp",
        "php": "language:PHP",
        "ruby": "language:Ruby",
    }
    rows = []
    errors = []
    for skill, q in queries.items():
        try:
            r = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": f"{q} created:2026-01-01..2026-11-12", "per_page": 1},
                headers={"Accept": "application/vnd.github+json"},
                timeout=30,
            )
            if r.status_code != 200:
                errors.append(f"{skill}: HTTP {r.status_code}")
            else:
                rows.append({
                    "skill": skill, "metric": "repositories_created",
                    "value": int(r.json().get("total_count", 0)),
                    "window_start": "2026-01-01", "window_end": "2026-11-12",
                    "source_url": "https://api.github.com/search/repositories",
                })
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{skill}: {type(exc).__name__}")
        time.sleep(7)
    out = pd.DataFrame(rows)
    if not out.empty:
        out.to_csv(PROC_DIR / "github_activity.csv", index=False)
        if use_cache:
            _json_cache_save(GITHUB_CACHE_PATH, {
                "fetched_at": RUN_TS, "rows": rows, "errors": errors,
            })
    return out, {"status": "ok" if rows else "failed", "rows": int(len(out)), "errors": errors}


def load_bls(cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS,
             use_cache: bool = True) -> Tuple[pd.DataFrame, Dict]:
    if use_cache:
        cached = _json_cache_load(BLS_CACHE_PATH, cache_ttl_hours)
        if cached is not None:
            df = _bls_from_cache(cached)
            return df, {"status": "ok", "rows": int(len(df)), "detail": "cache",
                        "cache_age_hours": cached.get("_cache_age_hours")}
    try:
        r = requests.post(
            "https://api.bls.gov/publicAPI/v1/timeseries/data/",
            json={"seriesid": ["JTS000000000000000JOL"], "startyear": "2024", "endyear": "2026"},
            timeout=60,
        )
        r.raise_for_status()
        j = r.json()
        series = j.get("Results", {}).get("series", [])
        if not series:
            return pd.DataFrame(), {"status": "failed", "detail": "No BLS series returned"}
        rows = []
        for d in series[0].get("data", []):
            rows.append({
                "year": int(d["year"]),
                "period": d["period"],
                "month": pd.Period(f"{d['year']}-{d['period'][1:]}", freq="M").strftime("%Y-%m"),
                "job_openings_thousands": float(d["value"]),
                "seasonally_adjusted": True,
            })
        out = pd.DataFrame(rows).sort_values("month")
        out.to_csv(PROC_DIR / "bls_jolts.csv", index=False)
        if use_cache and not out.empty:
            _json_cache_save(BLS_CACHE_PATH, {
                "fetched_at": RUN_TS, "message": j.get("message", []), "data": rows,
            })
        return out, {"status": "ok", "rows": int(len(out)), "detail": j.get("message", [])}
    except Exception as exc:  # noqa: BLE001
        return pd.DataFrame(), {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Aggregation / outputs
# ---------------------------------------------------------------------------

def load_tech_taxonomy() -> Set[str]:
    tech: Set[str] = set()
    for raw in CURATED_TECH_SKILLS.split():
        s = canonical_skill(raw)
        if s:
            tech.add(s)
    p = RAW_DIR / "datamatastudios_skill_demand_index.csv"
    if p.exists():
        df = pd.read_csv(p)
        for v in df["skill"].dropna():
            s = canonical_skill(v)
            if s:
                tech.add(s)
    p = PROJECT_ROOT / "weekly_skill_demand.csv"
    if p.exists():
        df = pd.read_csv(p, usecols=["skill"])
        for v in df["skill"].dropna().unique():
            s = canonical_skill(v)
            if s:
                tech.add(s)
    return {s for s in tech if s and s not in BLOCK_REGEX and s not in GENERIC_TECH_BLOCKLIST}


def aggregate_primary(source_rows: pd.DataFrame, tech_skills: Set[str]) -> pd.DataFrame:
    if source_rows.empty:
        return pd.DataFrame()
    prim = source_rows[source_rows["source_id"].isin(
        ["fliar_2026", "nextgig_2026_06", "joa_2026_10", "minmaxxxer_2026_10"]
    )].copy()
    prim = prim[prim["skill"].isin(tech_skills)]
    if prim.empty:
        return pd.DataFrame()
    # Equal-weight source average: avoids one large sample dominating a month.
    grp = prim.groupby(["month", "skill"]).agg(
        demand_share_pct=("demand_share_pct", "mean"),
        postings=("postings_with_skill", "sum"),
        source_count=("source_id", "nunique"),
        sources=("source_id", lambda x: "|".join(sorted(set(x)))),
        methods=("extraction_method", lambda x: "|".join(sorted(set(x)))),
    ).reset_index()
    grp["month_start"] = pd.to_datetime(grp["month"] + "-01")
    return grp[["month_start", "skill", "demand_share_pct", "postings", "source_count", "sources", "methods"]]


def build_current(source_rows: pd.DataFrame, datamata: pd.DataFrame, minmax: pd.DataFrame,
                  indeed: pd.DataFrame, yash: pd.DataFrame, nextgig: pd.DataFrame,
                  tech_skills: Set[str]) -> pd.DataFrame:
    frames = []
    if not datamata.empty:
        frames.append(datamata.assign(snapshot_date="2026-11-11"))
    if not minmax.empty:
        # Use the latest October week as the current cross-section.
        latest = minmax.sort_values("month").groupby("skill").tail(1)
        frames.append(latest.assign(snapshot_date="2026-10-09"))
    if not indeed.empty:
        latest = indeed.sort_values("month").groupby("skill").tail(1)
        frames.append(latest.assign(snapshot_date="2026-06-30"))
    if not yash.empty:
        frames.append(yash.assign(snapshot_date="2026-06-30"))
    if not nextgig.empty:
        frames.append(nextgig.assign(snapshot_date="2026-06-30"))
    if not frames:
        return pd.DataFrame()
    all_rows = pd.concat(frames, ignore_index=True)
    # Prefer the most recent snapshot for each skill.
    all_rows["snapshot_dt"] = pd.to_datetime(all_rows["snapshot_date"], errors="coerce")
    all_rows = all_rows.sort_values(["skill", "snapshot_dt", "source_id"])
    cur = all_rows.groupby("skill").tail(1).copy()
    # Attach source list from all snapshots that observed the skill.
    src = all_rows.groupby("skill")["source_id"].apply(lambda x: "|".join(sorted(set(x)))).rename("source_ids")
    cur = cur.merge(src, on="skill", how="left")
    cur["source_count"] = cur["source_ids"].apply(lambda x: len(set(str(x).split("|"))) if isinstance(x, str) else 0)
    cur = cur[cur["skill"].isin(tech_skills)]
    cols = ["skill", "snapshot_date", "demand_share_pct", "postings_with_skill", "source_ids", "source_count", "extraction_method"]
    if "category" in cur.columns:
        cols.append("category")
    if "required_share_pct" in cur.columns:
        cols.append("required_share_pct")
    return cur[cols].sort_values("demand_share_pct", ascending=False)


def baseline_2023() -> pd.DataFrame:
    p = PROJECT_ROOT / "weekly_skill_demand.csv"
    if not p.exists():
        return pd.DataFrame(columns=["skill", "baseline_2023_share_pct"])
    df = pd.read_csv(p, usecols=["skill", "demand"])
    df["skill"] = df["skill"].apply(canonical_skill)
    total = float(df["demand"].sum())
    out = df.groupby("skill")["demand"].sum().reset_index()
    out["baseline_2023_share_pct"] = out["demand"] / total * 100.0 if total else 0.0
    return out[["skill", "baseline_2023_share_pct"]]


def build_discovery(source_rows: pd.DataFrame, current: pd.DataFrame, baseline: pd.DataFrame,
                    tech_skills: Set[str]) -> pd.DataFrame:
    if source_rows.empty:
        return pd.DataFrame()
    all_rows = source_rows.copy()
    all_rows = all_rows[all_rows["skill"].isin(tech_skills)]
    all_rows["month_dt"] = pd.to_datetime(all_rows["month"] + "-01")
    g = all_rows.groupby("skill").agg(
        first_seen=("month", "min"),
        last_seen=("month", "max"),
        months_observed=("month", "nunique"),
        max_share_pct=("demand_share_pct", "max"),
        source_ids=("source_id", lambda x: "|".join(sorted(set(x)))),
    ).reset_index()
    if not current.empty:
        cur = current[["skill", "demand_share_pct"]].rename(columns={"demand_share_pct": "recent_share_pct"})
        g = g.merge(cur, on="skill", how="left")
    else:
        g["recent_share_pct"] = np.nan
    g = g.merge(baseline, on="skill", how="left")
    g["baseline_2023_share_pct"] = g["baseline_2023_share_pct"].fillna(0.0)
    g["recent_share_pct"] = g["recent_share_pct"].fillna(0.0)
    g["new_vs_2023"] = g["baseline_2023_share_pct"] <= 0.01
    g["emerging"] = (
        (g["first_seen"] >= "2025-01")
        & (g["recent_share_pct"] >= 0.05)
        & (g["new_vs_2023"] | (g["months_observed"] <= 6))
    )
    return g[["skill", "first_seen", "last_seen", "months_observed", "recent_share_pct",
              "baseline_2023_share_pct", "new_vs_2023", "emerging", "source_ids", "max_share_pct"]].sort_values(
        ["emerging", "recent_share_pct"], ascending=[False, False])


def write_outputs(source_rows: pd.DataFrame, monthly: pd.DataFrame, current: pd.DataFrame,
                  discovery: pd.DataFrame, aux: Dict[str, Tuple[pd.DataFrame, Dict]],
                  state: Optional[dict] = None, run_label: str = "") -> None:
    """Write processed tables, then update registry and manifest incrementally.

    Registry and manifest are rewritten after each file so an interrupted run
    still leaves a coherent provenance record of what completed.
    """
    steps: List[str] = []

    def _write(name: str, df: pd.DataFrame) -> None:
        df.to_csv(PROC_DIR / name, index=False)
        steps.append(name)
        _flush_provenance(aux, state, run_label, steps)

    _write("source_skill_monthly.csv", source_rows)
    _write("skill_demand_monthly.csv", monthly)
    _write("current_skill_demand.csv", current)
    _write("skill_discovery.csv", discovery)

    # Update registry statuses and file metadata.
    for s in SOURCE_REGISTRY:
        sid = s["id"]
        if sid in aux:
            _, meta = aux[sid]
            s["status"] = meta.get("status", "pending")
            s["rows"] = meta.get("rows")
            s["months"] = meta.get("months")
            s["date_min"] = meta.get("date_min")
            s["date_max"] = meta.get("date_max")
            s["detail"] = meta.get("detail")
            s["errors"] = meta.get("errors")
        # Attach local raw file metadata when known.
        for key, fname in [
            ("fliar_2026", "fliar_job_postings_2026_sample.csv"),
            ("nextgig_2026_06", "nextgig_jobs_2026_06.parquet"),
            ("joa_2026_10", "joa_employer_direct_2026_10.jsonl"),
            ("minmaxxxer_2026_10", "minmaxxxer_job_postings_2026_10.csv"),
            ("indeed_sample_2026", "indeed_jobs_sample_2026.csv"),
            ("datamatastudios_2026_11", "datamatastudios_skill_demand_index.csv"),
            ("yash_2026_overall", "yash_skills_2026_overall.csv"),
        ]:
            if s["id"] == key:
                p = RAW_DIR / fname
                if p.exists():
                    s["local_path"] = str(p.relative_to(PROJECT_ROOT))
                    s["bytes"] = p.stat().st_size
                    s["sha256"] = sha256_file(p)
        s["collected_at"] = RUN_TS

    _flush_provenance(aux, state, run_label, steps)


def _flush_provenance(aux: Dict[str, Tuple[pd.DataFrame, Dict]], state: Optional[dict],
                      run_label: str, completed: Sequence[str]) -> None:
    """Rewrite registry + manifest to reflect current progress."""
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(SOURCE_REGISTRY, f, indent=2, ensure_ascii=False)

    manifest = {
        "run_timestamp_utc": RUN_TS,
        "run_label": run_label,
        "pipeline_version": PIPELINE_VERSION,
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "sources": [{k: s.get(k) for k in ["id", "status", "rows", "months", "date_min", "date_max"]} for s in SOURCE_REGISTRY],
        "completed_outputs": list(completed),
        "outputs": {},
    }
    for f in ["source_skill_monthly.csv", "skill_demand_monthly.csv", "current_skill_demand.csv",
              "skill_discovery.csv", "github_activity.csv", "bls_jolts.csv"]:
        p = PROC_DIR / f
        if p.exists():
            try:
                rows = int(len(pd.read_csv(p)))
            except Exception:  # noqa: BLE001
                rows = -1
            manifest["outputs"][f] = {"rows": rows, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
    if state is not None:
        manifest["state"] = {
            "completed_steps": state.get("completed_steps", []),
            "started_at": state.get("started_at"),
            "resumed": state.get("resumed", False),
        }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def _reuse_outputs_if_valid() -> bool:
    """Reuse existing processed tables when every required output validates."""
    specs = {
        "source_skill_monthly.csv": ["month", "skill", "source_id", "demand_share_pct"],
        "skill_demand_monthly.csv": ["month_start", "skill", "demand_share_pct"],
        "current_skill_demand.csv": ["skill", "demand_share_pct"],
        "skill_discovery.csv": ["skill", "first_seen", "emerging"],
    }
    for fname, cols in specs.items():
        ok, detail = _validate_csv(PROC_DIR / fname, cols)
        if not ok:
            print(f"  reuse rejected: {fname}: {detail}", flush=True)
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="CoreNex market-data ingestion pipeline")
    ap.add_argument("--no-cache", action="store_true", help="Ignore cached API/vocabulary responses")
    ap.add_argument("--cache-ttl-hours", type=float, default=DEFAULT_CACHE_TTL_HOURS,
                    help="Max age (hours) for cached API responses (default 24)")
    ap.add_argument("--force", action="store_true", help="Recompute even if outputs are valid")
    ap.add_argument("--reuse", action="store_true",
                    help="Reuse valid processed outputs without recomputing")
    args = ap.parse_args()
    use_cache = not args.no_cache

    state = _state_load()
    resumed = state.get("started_at") and state.get("started_at") != RUN_TS
    if resumed:
        print(f"Resuming pipeline (started {state.get('started_at')}); "
              f"completed: {state.get('completed_steps')}", flush=True)

    prog = Progress("ingest")
    print("CoreNex market-data ingestion")
    print("Raw dir:", RAW_DIR)
    print("Processed dir:", PROC_DIR)
    print("Cache dir:", CACHE_DIR)

    if args.reuse and not args.force and _reuse_outputs_if_valid():
        prog.step("reuse", "valid outputs present")
        print("Reusing existing processed outputs (use --force to rebuild).")
        prog.done()
        return 0

    # Download the small files first so vocabulary building has full coverage.
    prog.step("download snapshots")
    for sid in ["datamatastudios_2026_11", "yash_2026_overall"]:
        ok, detail = download(SOURCE_BY_ID[sid]["file_url"], RAW_DIR / {
            "datamatastudios_2026_11": "datamatastudios_skill_demand_index.csv",
            "yash_2026_overall": "yash_skills_2026_overall.csv",
        }[sid])
        print(f"  {sid}: {detail}")

    prog.step("vocabulary")
    vocab_counts, extractor, vocab_meta = build_vocabulary(use_cache=use_cache)
    tech_skills = load_tech_taxonomy()
    print(f"Vocabulary ({vocab_meta.get('detail')}): {len(vocab_counts)} raw skill names; "
          f"tech taxonomy: {len(tech_skills)} skills", flush=True)

    aux: Dict[str, Tuple[pd.DataFrame, Dict]] = {}
    frames = []

    prog.step("source adapters")
    for fn, sid in [
        (load_fliar, "fliar_2026"),
        (load_nextgig, "nextgig_2026_06"),
        (load_joa, "joa_2026_10"),
        (load_minmaxxxer, "minmaxxxer_2026_10"),
        (load_indeed_sample, "indeed_sample_2026"),
        (load_datamatastudios, "datamatastudios_2026_11"),
        (load_yash, "yash_2026_overall"),
    ]:
        print(f"Loading {sid} ...", flush=True)
        try:
            if sid == "yash_2026_overall":
                df, meta = fn()
            else:
                df, meta = fn(extractor)
        except Exception as exc:  # noqa: BLE001
            df, meta = pd.DataFrame(), {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"}
        aux[sid] = (df, meta)
        state.setdefault("sources", {})[sid] = {"status": meta.get("status"), "rows": meta.get("rows")}
        print(f"  status={meta.get('status')} rows={meta.get('rows')} months={meta.get('months')}", flush=True)
        if not df.empty:
            frames.append(df)
        _state_save(state)

    prog.step("aggregate")
    source_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not source_rows.empty:
        source_rows = source_rows[source_rows["skill"].isin(tech_skills)].copy()
    monthly = aggregate_primary(source_rows, tech_skills)

    # Fill the primary monthly grid Jan-Oct 2026 so every observed skill has a
    # continuous series. Missing source-months mean zero observed postings.
    if not monthly.empty:
        months = [d.strftime("%Y-%m") for d in PRIMARY_MONTHS]
        skills = sorted(monthly["skill"].unique())
        idx = pd.MultiIndex.from_product([pd.to_datetime([m + "-01" for m in months]), skills],
                                         names=["month_start", "skill"])
        monthly = (monthly.set_index(["month_start", "skill"])
                   .reindex(idx)
                   .reset_index())
        monthly["demand_share_pct"] = monthly["demand_share_pct"].fillna(0.0)
        monthly["postings"] = monthly["postings"].fillna(0).astype(int)
        monthly["source_count"] = monthly["source_count"].fillna(0).astype(int)
        monthly["sources"] = monthly["sources"].fillna("")
        monthly["methods"] = monthly["methods"].fillna("")

    prog.step("current + discovery")
    current = build_current(
        source_rows,
        aux.get("datamatastudios_2026_11", (pd.DataFrame(), {}))[0],
        aux.get("minmaxxxer_2026_10", (pd.DataFrame(), {}))[0],
        aux.get("indeed_sample_2026", (pd.DataFrame(), {}))[0],
        aux.get("yash_2026_overall", (pd.DataFrame(), {}))[0],
        aux.get("nextgig_2026_06", (pd.DataFrame(), {}))[0],
        tech_skills,
    )
    baseline = baseline_2023()
    discovery = build_discovery(source_rows, current, baseline, tech_skills)

    prog.step("aux sources (GitHub/BLS)")
    gh, gh_meta = load_github(cache_ttl_hours=args.cache_ttl_hours, use_cache=use_cache)
    aux["github_trends"] = (gh, gh_meta)
    print(f"  GitHub: {gh_meta.get('detail') or gh_meta.get('status')} rows={gh_meta.get('rows')}", flush=True)
    bls, bls_meta = load_bls(cache_ttl_hours=args.cache_ttl_hours, use_cache=use_cache)
    aux["bls_jolts"] = (bls, bls_meta)
    print(f"  BLS: {bls_meta.get('detail')} rows={bls_meta.get('rows')}", flush=True)

    prog.step("write outputs")
    write_outputs(source_rows, monthly, current, discovery, aux, state=state,
                  run_label="full" if not resumed else "resume")
    state.setdefault("completed_steps", [])
    for name in ["source_skill_monthly.csv", "skill_demand_monthly.csv",
                 "current_skill_demand.csv", "skill_discovery.csv",
                 "github_activity.csv", "bls_jolts.csv"]:
        if name not in state["completed_steps"]:
            state["completed_steps"].append(name)
    state["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _state_save(state)

    print("Wrote:", PROC_DIR)
    print("Monthly rows:", len(monthly), "skills:", monthly["skill"].nunique() if not monthly.empty else 0)
    print("Current rows:", len(current), "discovery rows:", len(discovery))
    prog.done()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())