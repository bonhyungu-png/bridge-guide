# -*- coding: utf-8 -*-
"""웹 아티팩트(단일 HTML)에 박아 넣을 데이터 번들을 만든다.

data/파생/{본문,본문표}와 판정규칙 jsonl을 하나의 JSON으로 합쳐
scratchpad에 저장한다. 이 JSON을 아티팩트 HTML의 <script type="application/json">에
그대로 붙여 넣으면 어디서 열든 서버 없이 동작한다.

사용:
    python build/20_아티팩트_데이터.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "build" / "artifact_data.json"

NUMBERED = re.compile(r"^표(?P<no>\d+\.\d+(?:의\d+)?)\s+(?P<title>.+)$")
UNNUMBERED = re.compile(r"^표_(?P<title>.+)$")


def squash(s: str) -> str:
    return re.sub(r"[\s:：·・]+", "", s or "")


def load_tables() -> dict:
    tables = {}
    for 판본폴더 in sorted((DATA / "파생" / "본문표").glob("안전점검진단_교량@*")):
        year = 판본폴더.name.split("@", 1)[1]
        for f in sorted(판본폴더.glob("*.md")):
            stem = f.stem
            m = NUMBERED.match(stem)
            if m:
                title, number = m.group("title").strip(), m.group("no")
            else:
                m = UNNUMBERED.match(stem)
                if not m:
                    continue
                title, number = m.group("title").strip(), None
            key = squash(title)
            tables.setdefault(key, {"제목": title, "연도별": {}})
            tables[key]["연도별"][year] = {
                "번호": number,
                "내용": f.read_text("utf-8"),
            }
    return tables


def load_bodies() -> dict:
    bodies = {}
    for 판본폴더 in sorted((DATA / "파생" / "본문").glob("안전점검진단_교량@*")):
        year = 판본폴더.name.split("@", 1)[1]
        bodies[year] = []
        for f in sorted(판본폴더.glob("*.md")):
            bodies[year].append({"절": f.stem, "내용": f.read_text("utf-8")})
    return bodies


def load_rules() -> dict:
    rules = {}
    for f in sorted((DATA / "파생").glob("안전점검진단_교량@*_판정규칙.jsonl")):
        year = f.stem.split("@", 1)[1].split("_", 1)[0]
        rows = [json.loads(line) for line in f.read_text("utf-8").splitlines() if line.strip()]
        # 아티팩트에서 안 쓰는 필드는 뺀다(용량 절약).
        trimmed = []
        for r in rows:
            trimmed.append({
                "부재": r.get("부재"), "분류": r.get("분류"), "항목": r.get("항목"),
                "지표": r.get("지표"), "등급": r.get("등급"), "연산": r.get("연산"),
                "값": r.get("값"), "최소": r.get("최소"), "최대": r.get("최대"),
                "최소포함": r.get("최소포함"), "최대포함": r.get("최대포함"),
                "단위": r.get("단위"), "원문": r.get("원문"),
                "표": (r.get("출처") or {}).get("표"), "면": (r.get("출처") or {}).get("면"),
            })
        rules[year] = trimmed
    return rules


def main():
    bundle = {
        "생성": "20_아티팩트_데이터.py",
        "연도목록": sorted({p.name.split("@", 1)[1]
                          for p in (DATA / "파생" / "본문표").glob("안전점검진단_교량@*")}),
        "표": load_tables(),
        "본문": load_bodies(),
        "판정규칙": load_rules(),
    }
    OUT.write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"저장: {OUT}  ({OUT.stat().st_size / 1e6:.2f} MB)")
    print(f"연도: {bundle['연도목록']}")
    print(f"표 앵커 {len(bundle['표'])}개")
    print(f"본문 절 (연도별): {[(y, len(v)) for y, v in bundle['본문'].items()]}")
    print(f"판정규칙 (연도별): {[(y, len(v)) for y, v in bundle['판정규칙'].items()]}")


if __name__ == "__main__":
    main()
