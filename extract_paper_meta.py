"""Extract core metadata and reviewed deep entities from five arXiv PDFs.

Core header fields are retrieved from arXiv Atom API. Deep entity fields are
paper-specific reviewed annotations in config/paper_overrides.json; the script
validates these annotations against extracted paper text and records evidence
checks in output/run_report.json. OCR is attempted for pages with little/no text.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import fitz

ROOT = Path(__file__).resolve().parent
IDS = ["2503.18382", "2510.13998", "2607.18859", "2507.23370", "2503.11651"]
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
PAPERS_DIR = ROOT / "papers"
OUTPUT_DIR = ROOT / "output"
CONFIG_PATH = ROOT / "config" / "paper_overrides.json"
USER_AGENT = "FrontierAtlasInternTrial/1.0 (academic metadata extraction)"
MIN_TEXT_CHARS = 300
MIN_PAGE_TEXT_CHARS = 40


def fetch_bytes(url: str, attempts: int = 3, timeout: int = 90) -> bytes:
    """Fetch a URL with a descriptive User-Agent and bounded exponential retry."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def clean_text(value: str | None) -> str:
    """Normalize whitespace and repair common PDF line-wrap hyphenation."""
    text = (value or "").replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=[a-z])", "", text)
    text = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\emph\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def get_arxiv_metadata(ids: list[str]) -> dict[str, dict[str, Any]]:
    url = "https://export.arxiv.org/api/query?id_list=" + ",".join(ids)
    root = ET.fromstring(fetch_bytes(url))
    metadata: dict[str, dict[str, Any]] = {}
    for entry in root.findall("a:entry", ATOM_NS):
        entry_url = entry.findtext("a:id", default="", namespaces=ATOM_NS)
        match = re.search(r"abs/(\d{4}\.\d{4,5})", entry_url)
        if not match:
            continue
        paper_id = match.group(1)
        authors = [
            clean_text(author.findtext("a:name", default="", namespaces=ATOM_NS))
            for author in entry.findall("a:author", ATOM_NS)
        ]
        metadata[paper_id] = {
            "title": clean_text(entry.findtext("a:title", default="", namespaces=ATOM_NS)),
            "authors": [name for name in authors if name],
            "abstract": clean_text(entry.findtext("a:summary", default="", namespaces=ATOM_NS)),
            "publication_date": (entry.findtext("a:published", default="", namespaces=ATOM_NS) or "")[:10] or None,
        }
    return metadata


def extract_pdf_text(paper_id: str) -> tuple[str, dict[str, Any]]:
    """Download a PDF, extract selectable text, OCR low-text pages when possible."""
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = PAPERS_DIR / f"{paper_id}.pdf"
    if not pdf_path.exists() or pdf_path.stat().st_size < 1_000:
        pdf_path.write_bytes(fetch_bytes(f"https://arxiv.org/pdf/{paper_id}.pdf"))

    page_stats: list[dict[str, Any]] = []
    page_texts: list[str] = []
    ocr_pages: list[int] = []
    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text("text", sort=True) or ""
            used_ocr = False
            if len(page_text.strip()) < MIN_PAGE_TEXT_CHARS:
                try:
                    text_page = page.get_textpage_ocr(language="eng", dpi=200, full=True)
                    ocr_text = page.get_text("text", textpage=text_page, sort=True) or ""
                    if len(ocr_text.strip()) > len(page_text.strip()):
                        page_text = ocr_text
                        used_ocr = True
                        ocr_pages.append(page_number)
                except Exception as exc:
                    # OCR is optional: retain selectable text and expose the issue in report.
                    page_stats.append({"page": page_number, "ocr_error": str(exc)})
            page_texts.append(page_text)
            page_stats.append({"page": page_number, "characters": len(page_text), "ocr_used": used_ocr})

    full_text = clean_text("\n".join(page_texts))
    if len(full_text) < MIN_TEXT_CHARS:
        raise ValueError(
            f"Only {len(full_text)} text characters extracted. PDF may be scanned; "
            "install Tesseract OCR and ensure it is on PATH."
        )
    return full_text, {
        "pdf_path": str(pdf_path.relative_to(ROOT)),
        "pdf_pages": len(page_texts),
        "pdf_text_characters": len(full_text),
        "ocr_pages": ocr_pages,
        "page_details": page_stats,
    }


def normalize_github_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"https?://github\.com/([^/\s]+)/([^/\s?#]+)", url.strip())
    if not match:
        raise ValueError(f"Not a GitHub repository URL: {url}")
    return f"https://github.com/{match.group(1)}/{match.group(2).removesuffix('.git')}"


def find_evidence_snippet(text: str, term: str, window: int = 220) -> str | None:
    """Return a short source passage around the first case-insensitive match."""
    if not term:
        return None
    match = re.search(re.escape(term), text, flags=re.IGNORECASE)
    if not match:
        return None
    start = max(0, match.start() - window // 2)
    end = min(len(text), match.end() + window // 2)
    return text[start:end].strip()


def discover_candidate_evidence(text: str) -> dict[str, list[dict[str, str]]]:
    """Surface review candidates from PDF text; candidates are not auto-promoted to facts."""
    patterns = {
        "benchmark_or_dataset_candidates": re.compile(
            r"\b(?:SWE-bench(?:\s+Verified)?|RealEstate10K|CO3Dv2|ScanNet(?:-1500)?|"
            r"ETH3D|DTU|Tanks and Temples|UniMERNet|CNN/DailyMail)\b", re.IGNORECASE
        ),
        "metric_claim_candidates": re.compile(
            r"(?:Pass@1|AUC@\d+|accuracy|F1(?:-score)?|Chamfer(?: Distance)?|"
            r"inference speed|memory savings|\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*x)",
            re.IGNORECASE,
        ),
    }
    found: dict[str, list[dict[str, str]]] = {}
    for label, pattern in patterns.items():
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        for match in pattern.finditer(text):
            start = max(0, match.start() - 180)
            end = min(len(text), match.end() + 220)
            snippet = re.sub(r"\s+", " ", text[start:end]).strip()
            key = snippet.casefold()
            if key not in seen:
                seen.add(key)
                items.append({"matched_text": match.group(0), "snippet": snippet})
            if len(items) >= 40:
                break
        found[label] = items
    return found


def validate_override(paper_id: str, config: dict[str, Any], paper_text: str) -> dict[str, Any]:
    """Validate shape and report whether curated entities appear in the PDF text."""
    repo = normalize_github_url(config.get("github_url"))
    for field in ("tasks", "methods", "models", "datasets", "sota_claims"):
        if not isinstance(config.get(field, []), list):
            raise ValueError(f"{paper_id}: '{field}' must be a JSON array")
    for index, claim in enumerate(config.get("sota_claims", [])):
        required = {"benchmark", "metric", "value", "comparison_target"}
        if not isinstance(claim, dict) or not required.issubset(claim):
            raise ValueError(f"{paper_id}: SOTA claim {index} missing {sorted(required)}")

    text_lower = paper_text.casefold()
    repo_evidence = False
    if repo:
        repo_evidence = repo.casefold() in text_lower or repo.removeprefix("https://github.com/").casefold() in text_lower
    model_mentions = [m for m in config.get("models", []) if str(m).casefold() in text_lower]
    dataset_mentions = [d for d in config.get("datasets", []) if str(d).casefold() in text_lower]
    configured_entity_evidence = {
        field: [
            {"entity": str(entity), "snippet": find_evidence_snippet(paper_text, str(entity))}
            for entity in config.get(field, [])
        ]
        for field in ("models", "datasets", "tasks", "methods")
    }
    return {
        "github_url_found_in_pdf_text": repo_evidence,
        "configured_model_mentions_found": model_mentions,
        "configured_dataset_mentions_found": dataset_mentions,
        "configured_model_count": len(config.get("models", [])),
        "configured_dataset_count": len(config.get("datasets", [])),
        "configured_entity_evidence": configured_entity_evidence,
        "discovered_candidates_for_manual_review": discover_candidate_evidence(paper_text),
        "note": "Candidates and text matches are evidence aids, not proof of experimental use; verify entities and numeric claims in the paper's methods/experiments/results sections.",
    }


def build_record(paper_id: str, metadata: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Build the requested output schema without adding implementation-only fields."""
    return {
        "arxiv_id": paper_id,
        "title": metadata["title"],
        "authors": metadata["authors"],
        "publication_date": metadata["publication_date"],
        "arxiv_pdf_url": f"https://arxiv.org/pdf/{paper_id}.pdf",
        "arxiv_page_url": f"https://arxiv.org/abs/{paper_id}",
        "github_url": normalize_github_url(config.get("github_url")),
        "is_official_code": bool(config.get("is_official_code", False)),
        "tasks": config.get("tasks", []),
        "methods": config.get("methods", []),
        "models": config.get("models", []),
        "datasets": config.get("datasets", []),
        "sota_claims": config.get("sota_claims", []),
        "abstract": metadata["abstract"],
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing reviewed configuration: {CONFIG_PATH}")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    metadata = get_arxiv_metadata(IDS)

    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    for paper_id in IDS:
        try:
            if paper_id not in metadata:
                raise ValueError("No arXiv Atom API record returned")
            if paper_id not in config:
                raise ValueError("No reviewed metadata configuration for this paper")
            pdf_text, pdf_report = extract_pdf_text(paper_id)
            evidence[paper_id] = {
                **pdf_report,
                **validate_override(paper_id, config[paper_id], pdf_text),
            }
            records.append(build_record(paper_id, metadata[paper_id], config[paper_id]))
            print(f"OK {paper_id}: {metadata[paper_id]['title']} ({pdf_report['pdf_text_characters']:,} chars; OCR pages: {pdf_report['ocr_pages']})")
        except Exception as exc:
            errors.append({"arxiv_id": paper_id, "error": str(exc)})
            print(f"FAILED {paper_id}: {exc}")

    output_path = OUTPUT_DIR / "extracted_papers.json"
    output_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    report = {
        "expected": len(IDS),
        "extracted": len(records),
        "errors": errors,
        "paper_evidence": evidence,
        "metadata_provenance": {
            "title_authors_abstract_publication_date": "arXiv Atom API",
            "github_tasks_methods_models_datasets_sota_claims": "reviewed config/paper_overrides.json, checked against extracted PDF text",
        },
    }
    (OUTPUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"expected": len(IDS), "extracted": len(records), "errors": errors}, indent=2))
    if errors:
        print("Some papers failed. See output/run_report.json.", file=sys.stderr)
        return 1
    print(f"SUCCESS: all {len(IDS)} papers processed. Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
