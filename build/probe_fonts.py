"""Phase 1 사전 조사 - 연도별 PDF의 글꼴 크기 계층이 같은지 확인한다.

DB/스크립트/공통.py는 크기계층 = {20.0:"절2", 15.0:"절3", 13.0:"목", 11.0:"본문"} 을
2026년판 기준으로 하드코딩한다. 다른 연도가 같은 크기를 쓰지 않으면
그 파이프라인을 그대로 소급 적용할 수 없다.

이 스크립트는 아무것도 바꾸지 않는다. 크기 분포와 각 크기가 실제로 무엇을
담고 있는지만 보고한다.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent.parent
PDF_ROOT = ROOT / "시설물의 안전 및 유지관리 세부지침.pdf"
FILENAME = "01. 시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편)_교량편.pdf"

# 2026년판 기준으로 하드코딩된 매핑 (DB/스크립트/공통.py)
BASELINE = {20.0: "절2", 15.0: "절3", 13.0: "목", 11.0: "본문"}

SECTION = re.compile(r"^(1\.\d+(?:\.\d+)?)\s*(.*)$")
ITEM = re.compile(r"^([가-힣])\.\s*(.*)$")
CAPTION = re.compile(r"^\[(표|그림)\s*([\d.]+(?:의\d+)?)\]\s*(.*)$")


def group_lines(page, tol: int = 1):
    """공통.py의 줄묶기와 같은 방식 - y좌표와 글꼴 크기로 줄을 묶는다."""
    buckets = defaultdict(list)
    for c in page.chars:
        key = (round(c["top"] / tol) * tol, round(c["size"], 1))
        buckets[key].append(c)

    lines = []
    for (top, size) in sorted(buckets):
        chars = sorted(buckets[(top, size)], key=lambda x: x["x0"])
        parts, prev = [], None
        for c in chars:
            if prev is not None and c["x0"] - prev["x1"] > prev["size"] * 0.28:
                parts.append(" ")
            parts.append(c["text"])
            prev = c
        text = "".join(parts).strip()
        if text:
            lines.append({"top": top, "size": size, "text": text})
    return lines


def probe(pdf_path: Path, max_pages: int | None = None) -> dict:
    size_count: Counter = Counter()
    size_samples: dict[float, list[str]] = defaultdict(list)
    size_roles: dict[float, Counter] = defaultdict(Counter)

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[:max_pages] if max_pages else pdf.pages
        total = len(pdf.pages)
        for page_no, page in enumerate(pages, 1):
            if page_no in (1, 2):  # 목차면
                continue
            for line in group_lines(page):
                size, text = line["size"], line["text"]
                size_count[size] += 1
                if len(size_samples[size]) < 4:
                    size_samples[size].append(text[:52])
                # 이 크기가 실제로 무엇을 담고 있는지 분류
                if SECTION.match(text):
                    size_roles[size]["절번호"] += 1
                elif ITEM.match(text):
                    size_roles[size]["목(가.나.다)"] += 1
                elif CAPTION.match(text):
                    size_roles[size]["표·그림캡션"] += 1

    return {
        "총면": total,
        "크기별줄수": size_count,
        "크기별표본": dict(size_samples),
        "크기별역할": dict(size_roles),
    }


def main(argv=None) -> int:
    years = argv or ["2023", "2024", "2026"]

    for year in years:
        pdf_path = PDF_ROOT / ("%s 교량 관련 법령" % year) / FILENAME
        print("=" * 70)
        print("%s년판" % year)
        print("=" * 70)

        if not pdf_path.exists():
            print("  PDF 없음: %s" % pdf_path.name)
            print("  (2022년은 HWP만 있어 변환이 선행돼야 한다)")
            print()
            continue

        r = probe(pdf_path)
        print("  총 %d면" % r["총면"])
        print()
        print("  %-8s %-8s %-14s %s" % ("크기", "줄수", "2026매핑", "표본"))
        print("  " + "-" * 66)

        for size, count in sorted(r["크기별줄수"].items(), key=lambda x: -x[1])[:10]:
            mapped = BASELINE.get(size, "-")
            roles = r["크기별역할"].get(size, Counter())
            role_txt = " ".join("%s:%d" % (k, v) for k, v in roles.most_common(2))
            sample = r["크기별표본"][size][0] if r["크기별표본"].get(size) else ""
            print("  %-8s %-8d %-14s %s" % (size, count, mapped, sample))
            if role_txt:
                print("  %-8s %-8s %-14s   -> %s" % ("", "", "", role_txt))
        print()

        missing = [s for s in BASELINE if s not in r["크기별줄수"]]
        if missing:
            print("  [!] 2026 매핑에 있는 크기가 이 판본에 없음: %s" % missing)
        else:
            print("  [OK] 2026 매핑의 네 크기가 모두 존재")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or None))
