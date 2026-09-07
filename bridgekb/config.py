"""경로와 설정. 다른 모듈은 여기를 통해서만 파일 위치를 안다."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 정본 데이터. 아직 연구_2 안으로 옮기기 전이라 연구_1을 가리킨다.
# BRIDGE_KB_DATA 환경변수로 덮어쓸 수 있다.
DATA_DIR = Path(os.environ.get(
    "BRIDGE_KB_DATA",
    ROOT.parent / "연구_1" / "data" / "안전점검진단_교량편",
))

RULES_PATH = Path(os.environ.get(
    "BRIDGE_KB_RULES",
    ROOT.parent / "DB" / "파생" / "안전점검진단_교량@2026_판정규칙.jsonl",
))

KNOWLEDGE_DIR = ROOT / "knowledge"
REPORT_DIR = KNOWLEDGE_DIR / "_report"
LAWS_DIR = KNOWLEDGE_DIR / "laws"

DEFAULT_YEAR = "2026"


def available_years() -> list[str]:
    """정본에 실제로 존재하는 연도 목록."""
    years = set()
    if DATA_DIR.exists():
        for p in DATA_DIR.glob("*/*/*"):
            if p.is_dir() and p.parent.name in ("text", "table") and p.name.isdigit():
                years.add(p.name)
    return sorted(years)
