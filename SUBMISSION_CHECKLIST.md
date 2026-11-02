# Submission checklist

- [ ] Install requirements in a clean Python environment.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `python extract_paper_meta.py` with internet access.
- [ ] Confirm `output/run_report.json` reports 5 extracted records and no errors.
- [ ] Review all model/dataset/benchmark annotations against the paper's experiment sections and tables.
- [ ] Confirm output JSON parses and contains the assignment's required keys.
- [ ] Submit `extract_paper_meta.py`, `requirements.txt`, `output/extracted_papers.json`, and `README.md`; include config, tests and run report as supporting files.
