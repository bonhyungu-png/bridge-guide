# -*- coding: utf-8 -*-
"""표 번호 -> 실제 PDF 물리 페이지의 지도를 새로 만든다.

표 캡션("[표 1.11] ...")으로 페이지를 찾을 수는 없다. 그 캡션 글자가 지금
원본 PDF(data/원본pdf/*.pdf)에서 텍스트로 추출되지 않기 때문이다 - 그림으로
렌더링된 것으로 보인다. 게다가 PDF가 보기 편하도록 2-up에서 1-up으로
다시 변환되면서 페이지 번호 자체가 밀렸다 - data/파생 쪽 마크다운에 박힌
"면:" 값(옛 2-up 기준)을 그대로 믿으면 엉뚱한 페이지가 나온다
(실제로 표1.11의 "면: 15"를 열어보면 케이블·교대 내용이었다. 진짜는 29면).

그래서 표 번호가 아니라 **그 표 안에만 나오는 단어**로 페이지를 찾는다.
표 셀이 여러 칸으로 나뉜 페이지는 줄 단위로 읽으면 옆 칸 글자와 순서가 섞이므로
(pdfnorm.logical_pages의 줄 묶기가 이런 표에서 깨진다), 문장 대신 pdfplumber의
단어 단위 추출(extract_words)로 낱말만 뽑아 쓴다 - 낱말 하나는 한 칸 안에서만
나오므로 섞임의 영향을 덜 받는다.

단어를 고르는 기준: 그 표의 "기준:" 문구에 나오는 4글자 이상 낱말 중,
같은 판본 전체에서 등장하는 페이지가 적은(=흔하지 않은) 것만 후보로 남기고,
후보 낱말이 가장 많이 겹치는 페이지를 그 표의 페이지로 삼는다.

출력: knowledge/출처페이지.json = {연도: {표번호: 물리면}}

사용:
    python build/16_출처페이지매핑.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bridgekb import pdfnorm  # noqa: E402

OUT = ROOT / "knowledge" / "출처페이지.json"

MIN_WORD_LEN = 4
RARE_PAGE_LIMIT = 3      # 이 판본 전체에서 등장 페이지가 이 개수 이하여야 특이 단어로 본다
MIN_VOTES = 2            # 후보 단어가 이만큼은 같은 페이지에서 겹쳐야 채택한다

WORD_SPLIT = re.compile(r"[\s,\(\)~％%\.·/×―〜]+")


def candidate_words(content: str) -> set:
    """표 마크다운의 '기준:' 문구에서 4글자 이상 낱말을 뽑는다."""
    words = set()
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("기준:"):
            continue
        text = line.split(":", 1)[1].strip()
        for w in WORD_SPLIT.split(text):
            w = w.strip("◦0123456789㎜％%.")
            if len(w) >= MIN_WORD_LEN:
                words.add(w)
    return words


def build_word_index(year: str) -> dict:
    """이 판본의 낱말 -> 등장하는 물리 페이지 집합."""
    index: dict = defaultdict(set)
    with pdfplumber.open(pdfnorm.pdf_path(year)) as pdf:
        for physical, page in enumerate(pdf.pages, 1):
            for w in page.extract_words():
                text = w["text"].strip("◦0123456789㎜％%.,()")
                if len(text) >= MIN_WORD_LEN:
                    index[text].add(physical)
    return index


def find_page(words: set, index: dict) -> int | None:
    rare = [w for w in words if 0 < len(index.get(w, ())) <= RARE_PAGE_LIMIT]
    votes = Counter()
    for w in rare:
        for p in index[w]:
            votes[p] += 1
    if not votes:
        return None
    page, count = votes.most_common(1)[0]
    return page if count >= min(MIN_VOTES, len(rare)) else None


NUMBERED = re.compile(r"^표(?P<no>\d+\.\d+(?:의\d+)?)\s")


def tables_for(year: str) -> dict:
    """그 판본의 번호 있는 표: {표번호: 마크다운 내용}."""
    folder = ROOT / "data" / "파생" / "본문표" / ("안전점검진단_교량@%s" % year)
    out = {}
    for f in sorted(folder.glob("*.md")):
        m = NUMBERED.match(f.stem)
        if m:
            out[m.group("no")] = f.read_text("utf-8")
    return out


def main() -> int:
    result: dict = {}
    for year in pdfnorm.available_years():
        if not pdfnorm.pdf_path(year).exists():
            print("%s: PDF 없음, 건너뜀" % year)
            continue
        print("%s 처리 중 (낱말 색인 만드는 중)..." % year)
        index = build_word_index(year)

        year_out: dict = {}
        matched = missed = 0
        for number, content in tables_for(year).items():
            page = find_page(candidate_words(content), index)
            if page is None:
                missed += 1
                continue
            year_out[number] = page
            matched += 1
        result[year] = year_out
        print("  %d개 매칭, %d개 실패 (표 %d개 중)" % (matched, missed, matched + missed))

    if not any(result.values()):
        # 한 건도 못 찾았는데 그대로 쓰면 이미 검증해 둔 지도가 통째로 날아간다.
        # PDF를 못 찾는 환경에서 이 스크립트를 돌리면 실제로 그렇게 됐다.
        print("아무 표도 찾지 못해 저장하지 않았습니다 -", OUT)
        return 1

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("")
    print("저장:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
