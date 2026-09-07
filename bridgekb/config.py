"""경로와 설정. 다른 모듈은 여기를 통해서만 파일 위치를 안다."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 정본 데이터. 플러그인 자체에 번들돼 있어(연구_2/data) 설치한 곳 어디서나
# 그대로 동작한다 - 밖에 있는 DB/나 연구_1/ 에 더 이상 의존하지 않는다.
# BRIDGE_KB_DATA 환경변수로 덮어쓸 수 있다.
DATA_ROOT = Path(os.environ.get("BRIDGE_KB_DATA", ROOT / "data"))

판본_접두 = "안전점검진단_교량"

# anchor 등 표 조회 도구가 보는 곳. 파일명은 표{번호} {제목}.md 또는
# 표_{제목}.md, 상위 폴더 이름이 판본(안전점검진단_교량@{연도})이다.
TABLE_DIR = DATA_ROOT / "파생" / "본문표"

# 본문 문단(표참조: 상호참조 포함). 절2 하나당 파일 하나.
BODY_DIR = DATA_ROOT / "파생" / "본문"

# 표 격자 원본(정본) - 02_표추출.py가 만든 JSON. concept/grade 도구가 쓸 예정.
SKELETON_DIR = DATA_ROOT / "정본"

RULES_PATH = Path(os.environ.get(
    "BRIDGE_KB_RULES",
    DATA_ROOT / "파생" / f"{판본_접두}@2026_판정규칙.jsonl",
))


def rules_path_for(year: str) -> Path:
    return DATA_ROOT / "파생" / f"{판본_접두}@{year}_판정규칙.jsonl"


# 구 이름 - anchor.py 등 기존 코드와의 호환용 별칭. 새 코드는 TABLE_DIR을 쓴다.
DATA_DIR = TABLE_DIR

KNOWLEDGE_DIR = ROOT / "knowledge"
REPORT_DIR = KNOWLEDGE_DIR / "_report"
LAWS_DIR = KNOWLEDGE_DIR / "laws"

DEFAULT_YEAR = "2026"


def available_years() -> list[str]:
    """정본에 실제로 존재하는 연도 목록."""
    years = set()
    if TABLE_DIR.exists():
        for p in TABLE_DIR.iterdir():
            if p.is_dir() and p.name.startswith(판본_접두 + "@"):
                years.add(p.name.split("@", 1)[1])
    return sorted(years)
