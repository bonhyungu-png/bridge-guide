"""bridgekb CLI - 모든 환경(Claude Code / Gemini CLI / API / 웹)의 단일 진입점.

에이전트는 이 CLI를 셸로 호출하고, API 프로바이더는 같은 함수를 function call로
부른다. 호출 경로만 다르고 실행되는 코드는 하나다.

모든 출력은 JSON이다.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import anchor, config, tools

NOT_BUILT = {
    "status": "not_built",
    "안내": "이 도구는 아직 지식 빌드가 필요합니다. `python -m bridgekb doctor`로 상태를 확인하세요.",
}


def cmd_doctor(_args) -> dict:
    """지식베이스 상태 점검 - 무엇이 준비됐고 무엇이 빠졌는지."""
    years = config.available_years()
    report = config.REPORT_DIR / "phase0.json"

    checks = {
        "정본 데이터": {
            "경로": str(config.DATA_DIR),
            "존재": config.DATA_DIR.exists(),
            "연도": years,
        },
        "판정규칙": {
            "경로": str(config.RULES_PATH),
            "존재": config.RULES_PATH.exists(),
        },
        "Phase0 진단": {
            "경로": str(report),
            "존재": report.exists(),
        },
        "개념 사전": {
            "경로": str(config.KNOWLEDGE_DIR / "concepts.json"),
            "존재": (config.KNOWLEDGE_DIR / "concepts.json").exists(),
        },
        "법령 캐시": {
            "경로": str(config.LAWS_DIR),
            "존재": config.LAWS_DIR.exists(),
        },
    }

    ready = [name for name, c in checks.items() if c["존재"]]
    missing = [name for name, c in checks.items() if not c["존재"]]

    result = {"status": "ok" if not missing else "incomplete",
              "준비됨": ready, "빠짐": missing, "상세": checks}

    if report.exists():
        data = json.loads(report.read_text(encoding="utf-8"))
        result["진단요약"] = {
            "표참조_정확도": data["표참조"]["정확도"],
            "표참조_깨짐": data["표참조"]["깨짐"],
            "지표명_오염": data["지표명"]["오염"],
            "법령참조_종류": len(data["법령참조"]),
            "표번호밀림": len(data["표번호밀림"]),
        }
    if missing:
        result["다음단계"] = "python build/00_validate.py 를 실행해 진단 리포트를 만드세요."
    return result


def cmd_anchor(args) -> dict:
    return anchor.lookup(args.query, args.year)


def cmd_grade(args) -> dict:
    """등급 판정 - MCP의 grade_lookup과 같은 함수를 부른다(답이 갈리면 안 된다)."""
    return tools.grade_lookup(args.member, args.indicator, args.value, args.year)


def cmd_search(args) -> dict:
    return tools.body_search(args.query, args.year)


def cmd_tools(_args) -> dict:
    """등록된 도구 명세. MCP로 노출되는 것과 같은 목록이다."""
    return {"tools": tools.descriptors()}


def cmd_mcp(_args) -> int:
    """MCP 서버를 stdio로 띄운다. 이 명령만 JSON을 찍지 않는다(프로토콜이 stdout을 쓴다)."""
    from . import mcp_server
    raise SystemExit(mcp_server.serve())


def cmd_stub(name):
    def _run(_args) -> dict:
        out = dict(NOT_BUILT)
        out["도구"] = name
        return out
    return _run


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="bridgekb",
        description="교량 안전점검 지침서 조회 도구")
    ap.add_argument("--year", default=None, help="판본 연도 (기본: 질의에 따라 자동)")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="지식베이스 상태 점검")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("anchor", help="표 조회 (번호 또는 제목). 연도별 번호 밀림을 경고한다")
    p.add_argument("query", help='예: "1.31" 또는 "일반교량 가중치"')
    p.set_defaults(func=cmd_anchor)

    p = sub.add_parser("grade", help="수치 -> 등급 판정")
    p.add_argument("member", help="부재명. 예: 콘크리트 바닥판")
    p.add_argument("indicator", help="지표명. 예: 균열폭")
    p.add_argument("value", help="실측값. 예: 0.25")
    p.set_defaults(func=cmd_grade)

    p = sub.add_parser("search", help="본문 검색")
    p.add_argument("query", help="검색어")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("tools", help="도구 명세 목록 (MCP로 노출되는 것과 동일)")
    p.set_defaults(func=cmd_tools)

    p = sub.add_parser("mcp", help="MCP 서버를 stdio로 실행 (AI 도구에 등록해 쓴다)")
    p.set_defaults(func=cmd_mcp)

    for name, help_text in [
        ("concept", "손상 이름 -> 정식 항목·분류 (함정 경고 포함)"),
        ("compare", "연도별 기준 비교"),
        ("law", "법령 원문 조회"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("args", nargs="*")
        p.set_defaults(func=cmd_stub(name))

    return ap


def main(argv=None) -> int:
    # 윈도우 콘솔 기본 인코딩(cp949)으로는 한글 JSON을 못 찍는다. 출력은 어느
    # 환경에서든 UTF-8이어야 파이프로 받는 쪽이 같은 것을 본다.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    ap = build_parser()
    args = ap.parse_args(argv)
    result = args.func(args)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    # 조회 결과가 없거나 지식이 덜 빌드된 것은 도구의 실패가 아니다.
    # 종료코드 1은 도구 자체가 못 돌았을 때만 쓴다 - 그래야 셸 체이닝이 끊기지 않는다.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
