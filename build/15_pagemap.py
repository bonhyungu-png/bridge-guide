"""표·그림의 인쇄 면번호 지도를 만든다.

기존 data/의 `면:` 값은 물리 PDF 면수라서 종이 지침서에서 찾을 수 없다.
2-up 판본(2023/2024)은 실제 면수의 절반이고, 1-up 판본도 표지 때문에 어긋난다.

    [표 1.11]  실제 인쇄면 1-27
               기존 data: 2022=29  2023=15  2024=15  2026=29   (전부 다름)

이 스크립트는 원본 PDF를 훑어 캡션이 붙은 논리 페이지의 **인쇄 면번호**를 뽑아
`knowledge/pagemap.json`에 저장한다. 조회 도구는 이 지도를 보고 인용한다.

사용:
    python build/15_pagemap.py                 # 전체 연도
    python build/15_pagemap.py --years 2026
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridgekb import pdfnorm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "knowledge" / "pagemap.json"


def build_year(year: str) -> dict:
    """한 연도의 캡션 -> 인쇄 면번호 지도."""
    entries: dict = {}
    unnumbered: list = []

    for page in pdfnorm.logical_pages(year):
        for line in page.lines:
            m = pdfnorm.CAPTION.match(line.text)
            if not m:
                continue
            kind, number = m.group(1), m.group(2).rstrip(".")
            title = line.text[m.end():].strip()
            key = "%s%s" % (kind, number)

            # 같은 캡션이 여러 면에 걸치면 처음 나온 곳을 쓴다.
            if key in entries:
                continue
            entries[key] = {
                "종류": kind,
                "번호": number,
                "제목": title,
                "인쇄면": page.printed,
                "물리면": page.physical,
                "면쪽": page.side,
            }
            if page.printed is None:
                unnumbered.append(key)

    return {"캡션": entries, "인쇄면없음": unnumbered}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="인쇄 면번호 지도 생성")
    ap.add_argument("--years", nargs="*", default=None)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    years = args.years or pdfnorm.available_years()
    result = {"판본": {}}

    for year in years:
        if not pdfnorm.pdf_path(year).exists():
            print("  %s: PDF 없음, 건너뜀" % year)
            continue
        layout = pdfnorm.detect_layout(year)
        print("  %s 처리 중 (%d-up, 배율 %.3f) ..." % (year, layout.up, layout.scale))
        data = build_year(year)
        data["레이아웃"] = {"배치": "%d-up" % layout.up, "글꼴배율": round(layout.scale, 4)}
        result["판본"][year] = data
        print("     캡션 %d개, 인쇄면 못 읽음 %d개"
              % (len(data["캡션"]), len(data["인쇄면없음"])))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("")
    print("저장: %s" % args.out)

    # 연도 간 인쇄면이 얼마나 옮겨졌는지 요약한다.
    all_keys = sorted({k for y in result["판본"].values() for k in y["캡션"]})
    moved = []
    for key in all_keys:
        pages = {y: d["캡션"][key]["인쇄면"]
                 for y, d in result["판본"].items() if key in d["캡션"]}
        if len({v for v in pages.values() if v}) > 1:
            moved.append((key, pages))

    print("")
    print("연도 간 인쇄면이 바뀐 캡션: %d개 / 전체 %d개" % (len(moved), len(all_keys)))
    for key, pages in moved[:15]:
        print("  %-10s %s" % (key, "  ".join("%s=%s" % kv for kv in sorted(pages.items()))))
    if len(moved) > 15:
        print("  ... 외 %d개" % (len(moved) - 15))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
