"""Phase 0 진단 - 정본 데이터의 참조 무결성과 지표명 품질을 측정한다.

이 스크립트는 아무것도 고치지 않는다. 현재 상태를 숫자로 확정하는 것이 목적이고,
그 숫자가 이후 개선의 baseline이 된다.

사용:
    python build/00_validate.py                    # 기본 경로 검사
    python build/00_validate.py --data <경로>
    python build/00_validate.py --rules <판정규칙.jsonl 경로>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# 지침서 본문이 표를 가리키는 방식: "표참조: <파일명과 동일한 문자열>"
TABLE_REF = re.compile(r"^표참조:\s*(.+?)\s*$", re.MULTILINE)

# 법령 참조. 「법」제2조 / 「도로법」제10조 / 「법」제12조제3항 등을 모두 잡는다.
LAW_REF = re.compile(
    r"「(?P<law>[^」]{1,30})」\s*제(?P<article>\d+)조(?:의(?P<sub>\d+))?"
    r"(?:\s*제(?P<para>\d+)항)?(?:\s*제(?P<item>\d+)호)?"
)

# 조항 번호 없이 이름만 나오는 외부 기준 - 링크 대상을 특정할 수 없다.
EXTERNAL_REF = re.compile(r"건설기준코드|한국산업규격|KS\s*[A-Z]\s*\d+|하천기본계획")

# 지표명 자리에 들어오면 안 되는 것들 (파서 오염 신호)
POLLUTION_RANGE = re.compile(r"^\d+(\.\d+)?\s*[㎜mm%]*\s*(이상|미만|이하|초과)")
POLLUTION_TRUNCATED = re.compile(r"(에\s*폭|단면의|,\s*[가-힣]{1,2}$)")


@dataclass
class Report:
    table_refs_total: int = 0
    table_refs_ok: int = 0
    table_refs_broken: list = field(default_factory=list)
    law_refs: Counter = field(default_factory=Counter)
    external_refs: Counter = field(default_factory=Counter)
    indicators_total: int = 0
    indicators_polluted: list = field(default_factory=list)
    indicator_synonyms: dict = field(default_factory=dict)
    table_number_shifts: list = field(default_factory=list)

    def as_dict(self) -> dict:
        pct = (100 * self.table_refs_ok / self.table_refs_total) if self.table_refs_total else 0.0
        return {
            "표참조": {
                "전체": self.table_refs_total,
                "정상": self.table_refs_ok,
                "깨짐": len(self.table_refs_broken),
                "정확도": "%.1f%%" % pct,
                "깨진목록": self.table_refs_broken,
            },
            "법령참조": dict(self.law_refs),
            "외부기준참조_미해결": dict(self.external_refs),
            "지표명": {
                "전체": self.indicators_total,
                "오염": len(self.indicators_polluted),
                "오염목록": self.indicators_polluted,
                "동의어후보": self.indicator_synonyms,
            },
            "표번호밀림": self.table_number_shifts,
        }


def _squash(text: str) -> str:
    """공백과 콜론을 지운 비교용 형태. 표기 흔들림을 흡수한다."""
    return re.sub(r"[\s:：]+", "", text)


def check_table_refs(data_dir: Path, rep: Report) -> None:
    """본문의 '표참조:' 문자열이 실제 표 파일명과 일치하는지 전수 검사."""
    for text_file in sorted(data_dir.glob("*/text/*/*.md")):
        year = text_file.parent.name
        section_dir = text_file.parent.parent.parent
        table_dir = section_dir / "table" / year
        content = text_file.read_text(encoding="utf-8")

        for ref in TABLE_REF.findall(content):
            rep.table_refs_total += 1
            if (table_dir / (ref + ".md")).exists():
                rep.table_refs_ok += 1
                continue
            # 왜 못 찾았는지 힌트를 남긴다 - 콜론/공백 차이가 대부분이다.
            target = _squash(ref)
            near = [p.stem for p in table_dir.glob("*.md") if _squash(p.stem) == target]
            rep.table_refs_broken.append({
                "연도": year,
                "절": section_dir.name,
                "참조문자열": ref,
                "실제파일": near[0] if near else None,
                "원인": "공백·콜론 표기 불일치" if near else "대응 파일 없음",
            })


def check_law_refs(data_dir: Path, rep: Report) -> None:
    """법령·외부기준 참조를 수집한다. 아직 연결 대상이 없으므로 목록만 만든다."""
    for md in sorted(data_dir.glob("*/*/*/*.md")):
        content = md.read_text(encoding="utf-8")
        for m in LAW_REF.finditer(content):
            label = "「%s」제%s조" % (m.group("law"), m.group("article"))
            if m.group("sub"):
                label += "의" + m.group("sub")
            if m.group("para"):
                label += "제%s항" % m.group("para")
            rep.law_refs[label] += 1
        for m in EXTERNAL_REF.finditer(content):
            rep.external_refs[m.group(0).strip()] += 1


def check_indicators(rules_path: Path, rep: Report) -> None:
    """판정규칙의 지표명 품질을 검사한다 - 구간값 혼입, 문장 잘림, 동의어 미통합."""
    if not rules_path.exists():
        return
    lines = rules_path.read_text(encoding="utf-8").splitlines()
    rules = [json.loads(line) for line in lines if line.strip()]
    indicators = sorted({r["지표"] for r in rules if r.get("지표")})
    rep.indicators_total = len(indicators)

    for name in indicators:
        reason = None
        if POLLUTION_RANGE.match(name):
            reason = "지표명이 아니라 구간값"
        elif name.count("(") != name.count(")"):
            reason = "괄호가 닫히지 않음"
        elif POLLUTION_TRUNCATED.search(name):
            reason = "문장이 잘림"
        if reason:
            rep.indicators_polluted.append({"지표": name, "원인": reason})

    # 공백을 없앴을 때 같아지면 동의어 후보다.
    groups = defaultdict(list)
    for name in indicators:
        groups[re.sub(r"\s+", "", name)].append(name)
    rep.indicator_synonyms = {k: v for k, v in groups.items() if len(v) > 1}


def check_table_shifts(data_dir: Path, rep: Report) -> None:
    """같은 표 제목이 연도마다 다른 번호를 갖는 경우를 찾는다."""
    pat = re.compile(r"^표(?P<no>[\d.]+(?:의\d+)?)\s+(?P<title>.+)$")
    by_title = defaultdict(dict)

    for table_file in sorted(data_dir.glob("*/table/*/*.md")):
        m = pat.match(table_file.stem)
        if not m:
            continue
        by_title[m.group("title").strip()][table_file.parent.name] = m.group("no")

    for title, per_year in sorted(by_title.items()):
        if len(set(per_year.values())) > 1:
            rep.table_number_shifts.append({
                "표제목": title,
                "연도별번호": dict(sorted(per_year.items())),
            })


def render(rep: Report) -> str:
    d = rep.as_dict()
    out = []
    add = out.append

    add("=" * 68)
    add("Phase 0 진단 리포트 - 교량편 정본 데이터 현황")
    add("=" * 68)

    t = d["표참조"]
    add("")
    add("[1] 표참조 링크 무결성")
    add("    전체 %d건 / 정상 %d건 / 깨짐 %d건  ->  정확도 %s"
        % (t["전체"], t["정상"], t["깨짐"], t["정확도"]))
    for b in t["깨진목록"][:20]:
        add("      - %s %s" % (b["연도"], b["절"]))
        add("        참조: %r" % b["참조문자열"])
        add("        실제: %r  (%s)" % (b["실제파일"], b["원인"]))
    if len(t["깨진목록"]) > 20:
        add("      ... 외 %d건" % (len(t["깨진목록"]) - 20))

    add("")
    add("[2] 법령 참조 (연결 대상 확보 필요)")
    if d["법령참조"]:
        for k, v in sorted(d["법령참조"].items(), key=lambda x: -x[1]):
            add("      %3d회  %s" % (v, k))
    else:
        add("      없음")

    add("")
    add("[3] 외부기준 참조 (조항 번호 없어 링크 불가 - 미해결로 관리)")
    for k, v in sorted(d["외부기준참조_미해결"].items(), key=lambda x: -x[1]):
        add("      %3d회  %s" % (v, k))

    i = d["지표명"]
    add("")
    add("[4] 지표명 품질")
    add("    전체 %d개 / 오염 %d개" % (i["전체"], i["오염"]))
    for p in i["오염목록"]:
        add("      - %r  ->  %s" % (p["지표"], p["원인"]))
    add("    동의어 후보 %d쌍:" % len(i["동의어후보"]))
    for _, names in sorted(i["동의어후보"].items()):
        add("      - " + " = ".join(repr(n) for n in names))

    add("")
    add("[5] 표 번호 연도별 밀림 (%d건)" % len(d["표번호밀림"]))
    for s in d["표번호밀림"]:
        pairs = "  ".join("%s=표%s" % (y, n) for y, n in s["연도별번호"].items())
        add("      - %s" % s["표제목"])
        add("        %s" % pairs)

    add("")
    add("=" * 68)
    return "\n".join(out)


def main(argv=None) -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="정본 데이터 진단")
    ap.add_argument("--data", type=Path,
                    default=root.parent / "연구_1" / "data" / "안전점검진단_교량편")
    ap.add_argument("--rules", type=Path,
                    default=root.parent / "DB" / "파생" / "안전점검진단_교량@2026_판정규칙.jsonl")
    ap.add_argument("--out", type=Path, default=root / "knowledge" / "_report")
    args = ap.parse_args(argv)

    if not args.data.exists():
        print("데이터 경로를 찾을 수 없습니다: %s" % args.data, file=sys.stderr)
        return 1

    rep = Report()
    check_table_refs(args.data, rep)
    check_law_refs(args.data, rep)
    check_indicators(args.rules, rep)
    check_table_shifts(args.data, rep)

    text = render(rep)
    print(text)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "phase0.json").write_text(
        json.dumps(rep.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "phase0.txt").write_text(text, encoding="utf-8")
    print("")
    print("리포트 저장: %s" % (args.out / "phase0.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
