# Research Paper OCR & Deep Metadata Extraction

A reproducible Python pipeline for the five arXiv papers in the FrontierAtlas 3-Day Intern Trial.

## What it does

1. Queries the arXiv Atom API for title, author list, abstract and publication date.
2. Downloads each arXiv PDF into `papers/` (or reuses an existing local copy).
3. Extracts selectable PDF text with PyMuPDF, repairing common line-wrap hyphenation.
4. Attempts page-level OCR for pages with very little selectable text using PyMuPDF's Tesseract integration (`Page.get_textpage_ocr`).
5. Builds the required JSON schema using paper-specific reviewed annotations in `config/paper_overrides.json` for official repositories, tasks, methods, models, datasets and SOTA claims.
6. Checks whether configured repository/model/dataset strings occur in the extracted PDF text and stores short evidence snippets for configured entities.
7. Surfaces benchmark/dataset-name and metric/result-pattern candidates from the PDF for manual review; these candidates are deliberately not promoted automatically into the final metadata because text matching alone cannot establish experimental use.
8. Records candidate snippets, configured-entity evidence, OCR page numbers and extraction statistics in `output/run_report.json` while keeping implementation-only evidence out of the assignment's `extracted_papers.json` schema.

**Important provenance distinction:** the arXiv Atom API supplies core header metadata. Deep entities and benchmark claims remain reviewed annotations. The script now adds evidence snippets and candidate discovery to accelerate review, but it does not claim full semantic extraction: a string appearing in a PDF does not prove that it was used in an experiment. Review the relevant experimental section/table before treating a dataset or claim as confirmed.

## Why repository links are explicitly mapped

A broad URL regex can select cited software dependencies or unrelated links. The project therefore uses a per-paper repository mapping in `config/paper_overrides.json`, normalized to `https://github.com/owner/repository`. The pipeline also checks whether the configured repository URL or owner/repository string appears in extracted paper text. PP-FormulaNet's abstract names both PaddleOCR and PaddleX; the required single `github_url` field uses PaddleOCR as the primary repository.

## Requirements

- Python 3.10 or newer (tested by the author on Python 3.14.7)
- Internet access for arXiv API and PDF downloads
- PyMuPDF 1.26.7
- For scanned/image-only pages: Tesseract OCR installed separately and available on PATH. OCR is attempted automatically for pages with fewer than 40 selectable-text characters. If Tesseract is unavailable, the run report records the OCR error; install Tesseract before processing image-only PDFs.

## Windows PowerShell setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python extract_paper_meta.py
```

If `python` opens Microsoft Store, use the full Python executable path:

```powershell
& "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe" -m pip install -r requirements.txt
& "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe" .\extract_paper_meta.py
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Output and deliverables

- `extract_paper_meta.py` — main pipeline
- `requirements.txt` — pinned Python dependency
- `output/extracted_papers.json` — five records using the assignment's target schema
- `README.md` — setup and provenance documentation
- `config/paper_overrides.json` — reviewed deep metadata annotations
- `output/run_report.json` — run summary, page-level extraction details, configured-entity evidence snippets and candidate snippets for manual review
- `tests/` — offline unit tests
- `papers/` — downloaded PDFs (created by the pipeline; not required to be committed)

## Notes on completeness and accuracy

An empty `datasets` array means no dataset was confidently annotated; the pipeline does not invent one. The PDF text extraction and optional OCR create searchable text, but identifying experimental use still requires semantic review. Numeric SOTA claims should be checked against the cited result table and should retain the exact benchmark, metric, value and comparison target. The `run_report.json` makes extraction evidence and provenance inspectable without changing the assignment's requested output schema.
