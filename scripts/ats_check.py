#!/usr/bin/env python3
"""ATS check: parse the resume PDF as plain text and score it against the vacancy.

Usage: python3 scripts/ats_check.py resume.pdf vacancy_keywords.txt

vacancy_keywords.txt:
    title: Senior Technical Product Manager
    years: 5
    # weight | keyword | variants that also count (comma-separated)
    3 | platform | platforms
    2 | A/B testing | A/B test, A/B tests, experimentation
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

SWIFT_EXTRACT = """import PDFKit
let d = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1]))!
print(d.string ?? "")
"""

SECTIONS = {
    "summary": ["summary", "profile", "about"],
    "experience": ["experience", "employment", "work history"],
    "education": ["education"],
    "skills": ["skills"],
}


def extract_text(pdf):
    try:
        import pypdf
        return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(pdf).pages)
    except ImportError:
        pass
    if shutil.which("pdftotext"):
        return subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout
    if shutil.which("swift"):
        with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as f:
            f.write(SWIFT_EXTRACT)
        out = subprocess.run(["swift", f.name, pdf], capture_output=True, text=True).stdout
        os.unlink(f.name)
        return out
    sys.exit("No PDF text extractor: pip install pypdf")


def read_keywords(path):
    title, years, kws = "", 0, []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("title:"):
            title = line.split(":", 1)[1].strip()
        elif line.lower().startswith("years:"):
            years = int(re.sub(r"\D", "", line) or 0)
        else:
            parts = [p.strip() for p in line.split("|")]
            weight, term = int(parts[0]), parts[1]
            variants = [term] + [v.strip() for v in (parts[2] if len(parts) > 2 else "").split(",") if v.strip()]
            kws.append((weight, term, variants))
    return title, years, kws


def found(text, phrase):
    pattern = r"(?<![A-Za-z0-9])" + re.escape(phrase.lower()).replace(r"\ ", r"[\s-]+") + r"(?![A-Za-z0-9])"
    return len(re.findall(pattern, text))


def main(pdf, kw_path):
    raw = extract_text(pdf)
    text = re.sub(r"\s+", " ", raw).lower()
    title, years, kws = read_keywords(kw_path)
    checks = []

    checks.append(("Text is extractable", len(text) > 1500, f"{len(text)} chars"))
    checks.append(("No broken characters", "\ufffd" not in raw, "replacement chars found" if "\ufffd" in raw else "ok"))
    split = sorted(set(re.findall(r"(?<![A-Za-z/])([B-HJ-Z] [a-z]{2,})", raw)))
    checks.append(("No words split by kerning", not split, f"{split[:5]} — add html {{ font-kerning: none; }}"))
    checks.append(("Email parsed", bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", raw)), ""))
    checks.append(("Phone parsed", bool(re.search(r"\+?\d[\d\s()-]{8,}\d", raw)), ""))
    checks.append(("LinkedIn parsed", "linkedin" in text, "add the URL or the word LinkedIn as a link text"))
    for name, words in SECTIONS.items():
        checks.append((f"Section heading: {name}", any(re.search(rf"\b{w}\b", text) for w in words), ""))
    ranges = re.findall(r"(?:19|20)\d\d\s*[–—-]\s*(?:(?:19|20)\d\d|present|now|н\. в\.)", text)
    checks.append(("Date ranges per job", len(ranges) >= 2, f"{len(ranges)} found"))
    if title:
        head = text[:400]
        checks.append(("Vacancy title in the header", title.lower() in head, f"expected «{title}» near the name"))
    if years:
        stated = [int(n) for n in re.findall(r"(\d+)\+?\s+years", text)]
        checks.append((f"Years of experience ≥ {years}", any(n >= years for n in stated), f"stated: {stated or 'none'}"))

    total = sum(w for w, _, _ in kws) or 1
    got, rows = 0, []
    for weight, term, variants in kws:
        hits = sum(found(text, v) for v in variants)
        if hits:
            got += weight
        rows.append((weight, term, hits))

    print(f"ATS check: {os.path.basename(pdf)}\n")
    print("Parsing")
    for name, ok, note in checks:
        print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" — {note}" if note and not ok else ""))
    print("\nKeywords (weight, keyword, hits)")
    for weight, term, hits in sorted(rows, key=lambda r: (r[2] > 0, -r[0])):
        print(f"  [{'ok' if hits else 'MISS'}] {weight} | {term} | {hits}")
    must = [r for r in rows if r[0] >= 3]
    must_cov = sum(1 for r in must if r[2]) / len(must) if must else 1
    score = got / total
    print(f"\nWeighted keyword coverage: {score:.0%}")
    print(f"Must-have (weight 3) coverage: {must_cov:.0%}")
    failed = [c for c in checks if not c[1]]
    verdict = "PASS" if not failed and score >= 0.8 and must_cov >= 0.9 else "FIX"
    print(f"Verdict: {verdict} (needs: all parsing ok, coverage ≥ 80%, must-have ≥ 90%)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
