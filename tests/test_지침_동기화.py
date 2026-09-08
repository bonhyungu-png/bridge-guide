"""행동 지침이 도구마다 갈라지지 않았는지 지킨다.

원본은 `skills/bridge-guide/SKILL.md` 하나다. CLAUDE.md · GEMINI.md · AGENTS.md 는
거기서 복사해 만든 것이고(build/30_지침_동기화.py), 손으로 고치면 도구마다
다른 규칙을 읽게 된다 - 이 프로젝트가 "어느 창에서 물어도 같은 답"을 목표로
하는 이상 그건 조용히 무너지는 실패다. 그래서 여기서 막는다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "build" / "30_지침_동기화.py"


def _sync_module():
    """파일명이 숫자로 시작해 일반 import가 안 된다 - 경로로 직접 불러온다."""
    spec = importlib.util.spec_from_file_location("지침동기화", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("filename", ["CLAUDE.md", "GEMINI.md", "AGENTS.md"])
def test_도구별_지침이_SKILL과_같다(filename):
    sync = _sync_module()
    want = sync.rendered(sync.TARGETS[filename])
    have = (ROOT / filename).read_text(encoding="utf-8")
    assert have == want, (
        "%s 가 SKILL.md와 어긋났습니다. "
        "python build/30_지침_동기화.py 를 돌리세요." % filename)


@pytest.mark.parametrize("filename", ["CLAUDE.md", "GEMINI.md", "AGENTS.md"])
def test_한줄_포인터가_아니라_본문이_들어_있다(filename):
    """@import 한 줄만 두면 Codex·Cursor·API 쪽에서는 지침이 없는 것과 같다."""
    text = (ROOT / filename).read_text(encoding="utf-8")
    assert "등급을 판정하지 않는다" in text, "절대 규칙 본문이 빠졌다"
    assert "grade_lookup" in text, "도구 안내가 빠졌다"
