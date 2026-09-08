# -*- coding: utf-8 -*-
"""행동 지침을 도구별 파일로 복사한다 - SKILL.md 하나에서 CLAUDE/GEMINI/AGENTS.md 로.

원본은 `skills/bridge-guide/SKILL.md` 하나뿐이다. 그런데 도구마다 읽는 파일이
다르고, **읽는 방식도 다르다**:

    Claude Code   CLAUDE.md   `@경로` 한 줄로 다른 파일을 끌어올 수 있다
    Gemini CLI    GEMINI.md   최신 버전은 `@경로`를 지원한다
    Codex CLI     AGENTS.md   @import 없다 - 파일에 적힌 글자가 전부다
    Cursor        .cursor/rules/*.mdc
    순수 API      아무것도 없다 - 사람이 프롬프트에 직접 붙여넣는다

그래서 "한 줄 포인터"로 두면 Codex·Cursor·API 쪽에서는 지침이 **통째로 없는
것과 같다**(파일에 `@./skills/...` 라는 글자만 들어 있게 된다). 중복을 감수하고
본문을 복사해 넣되, 손으로 고치지 못하게 자동 생성으로 만든다.

사용:
    python build/30_지침_동기화.py            # 세 파일을 다시 만든다
    python build/30_지침_동기화.py --check    # 어긋났는지만 본다 (테스트용, 0/1)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "bridge-guide" / "SKILL.md"

TARGETS = {
    "CLAUDE.md": "Claude Code",
    "GEMINI.md": "Gemini / Gemini CLI",
    "AGENTS.md": "Codex CLI · 그 밖의 AGENTS.md 를 읽는 도구",
}

HEADER = """<!-- 자동 생성 파일입니다. 고치지 마세요.
     원본: skills/bridge-guide/SKILL.md
     다시 만들기: python build/30_지침_동기화.py
     읽는 도구: %s -->

"""


def body() -> str:
    """SKILL.md에서 프런트매터(---로 감싼 머리말)를 걷어낸 본문."""
    text = SKILL.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.lstrip("\n")


def rendered(reader: str) -> str:
    return HEADER % reader + body()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="행동 지침을 도구별 파일로 복사")
    ap.add_argument("--check", action="store_true", help="다시 만들지 않고 어긋남만 확인")
    args = ap.parse_args(argv)

    stale = []
    for filename, reader in TARGETS.items():
        path = ROOT / filename
        want = rendered(reader)
        have = path.read_text(encoding="utf-8") if path.exists() else None
        if have == want:
            continue
        stale.append(filename)
        if not args.check:
            path.write_text(want, encoding="utf-8")

    if args.check:
        if stale:
            print("SKILL.md와 어긋난 파일: %s" % ", ".join(stale))
            print("python build/30_지침_동기화.py 를 돌리세요.")
            return 1
        print("세 파일 모두 SKILL.md와 같습니다.")
        return 0

    print("갱신: %s" % (", ".join(stale) if stale else "없음 (이미 같음)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
