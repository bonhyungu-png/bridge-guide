# -*- coding: utf-8 -*-
"""표 관련 데이터에 박힌 "면" 값을 실제 PDF 물리 페이지로 고쳐 쓴다.

data/파생 쪽 마크다운·판정규칙에 있는 "면" 값은 예전 PDF(2-up) 기준 물리
페이지라 지금 보기 편하게 1-up으로 다시 만든 PDF와 안 맞는다(표1.11이
"15면"이라고 적혀 있었지만 지금 PDF의 15쪽은 케이블·교대 내용이다. 진짜는
29쪽). 답 아래 "출처"에 그 PDF 쪽을 그대로 보여주려면 "면" 자체가 지금 PDF의
진짜 페이지여야 한다 - 그래서 조회할 때마다 표 번호로 다시 찾지 않고, 데이터에
직접 박아 넣는다.

먼저 build/16_출처페이지매핑.py를 돌려 knowledge/출처페이지.json을 만들어 둬야
한다(표 본문에만 나오는 낱말로 실제 PDF 페이지를 찾아 검증해 둔 값이다).

사용:
    python build/17_페이지값_보정.py            # 실제로 고친다
    python build/17_페이지값_보정.py --dry-run   # 무엇이 바뀔지만 센다
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PAGEMAP = ROOT / "knowledge" / "출처페이지.json"

MD_HEADER = re.compile(r"^면: (\d+)$", re.MULTILINE)
MD_TABLE_NO = re.compile(r"^표(?P<no>\d+\.\d+(?:의\d+)?)\s")


def fix_jsonl(year: str, table_pages: dict, dry: bool) -> int:
    path = DATA / "파생" / ("안전점검진단_교량@%s_판정규칙.jsonl" % year)
    if not path.exists():
        return 0
    lines = [line for line in path.read_text("utf-8").splitlines() if line.strip()]
    rows = [json.loads(line) for line in lines]
    changed = 0
    for row in rows:
        source = row.get("출처") or {}
        table = source.get("표")
        if table in table_pages and source.get("면") != table_pages[table]:
            source["면"] = table_pages[table]
            changed += 1
    if changed and not dry:
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
    return changed


def fix_markdown(year: str, table_pages: dict, dry: bool) -> int:
    folder = DATA / "파생" / "본문표" / ("안전점검진단_교량@%s" % year)
    if not folder.exists():
        return 0
    changed = 0
    for f in sorted(folder.glob("*.md")):
        m = MD_TABLE_NO.match(f.stem)
        if not m or m.group("no") not in table_pages:
            continue
        new_page = table_pages[m.group("no")]
        text = f.read_text("utf-8")
        hm = MD_HEADER.search(text)
        if not hm:
            continue
        old_page = hm.group(1)
        if old_page == str(new_page):
            continue
        new_text = MD_HEADER.sub("면: %d" % new_page, text)
        new_text = re.sub(r"(?<!\d)%s면\b" % re.escape(old_page), "%d면" % new_page, new_text)
        if new_text != text:
            changed += 1
            if not dry:
                f.write_text(new_text, encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="면 값을 실제 PDF 페이지로 보정")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not PAGEMAP.exists():
        print("먼저 돌리세요: python build/16_출처페이지매핑.py")
        return 1

    table_pages_by_year = json.loads(PAGEMAP.read_text("utf-8"))
    for year, table_pages in table_pages_by_year.items():
        n_json = fix_jsonl(year, table_pages, args.dry_run)
        n_md = fix_markdown(year, table_pages, args.dry_run)
        print("%s: 판정규칙 %d행, 마크다운 %d개 파일 수정%s"
              % (year, n_json, n_md, " (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
