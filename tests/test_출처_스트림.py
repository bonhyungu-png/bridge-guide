# -*- coding: utf-8 -*-
"""Claude Code stream-json 에서 출처를 뽑는 부분의 회귀 시험.

여기 있는 두 가지가 실제로 터졌던 것이다.
1) 권한 안내 줄은 message 가 문자열이라, dict 로 알고 .get 하면 죽는다.
2) 도구 이름 접두사가 설치 방식마다 달라서, 한쪽만 허용하면 권한 거부된다.
"""
import json

from bridgekb import engines


def _line(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def test_문자열_message_줄에_죽지_않는다():
    """플러그인 권한 안내 줄(message가 str)이 섞여도 파싱이 계속돼야 한다."""
    lines = [
        _line({"type": "system", "message": None}),
        _line({"type": "system",
               "message": "Claude requested permissions to use "
                          "mcp__plugin_bridge-guide_bridge-guide__grade_lookup, "
                          "but you haven't granted it yet."}),
    ]
    assert engines._sources_from_stream(lines) == []


def test_플러그인_접두사_도구결과에서도_출처를_뽑는다():
    """접두사가 mcp__plugin_..._... 여도 grade_lookup 으로 알아봐야 한다."""
    payload = {"found": True, "year": "2026",
               "source": {"table": "1.11", "page": 29}}
    lines = [
        _line({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1",
             "name": "mcp__plugin_bridge-guide_bridge-guide__grade_lookup"}]}}),
        _line({"type": "system", "message": "권한 안내 같은 문자열 줄"}),
        _line({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": json.dumps(payload, ensure_ascii=False)}]}}),
    ]
    assert engines._sources_from_stream(lines) == [
        {"year": "2026", "table": "1.11", "page": 29}]


def test_허용목록에_두_접두사가_모두_들어간다():
    """프로젝트로 붙이든 플러그인으로 붙이든 같은 도구가 허용돼야 한다."""
    allowed = engines.allowed_tool_names()
    assert "mcp__bridge-guide__grade_lookup" in allowed
    assert "mcp__plugin_bridge-guide_bridge-guide__grade_lookup" in allowed
    # 도구 6개 x 접두사 2개
    assert len(allowed) == len(engines.tools.SPECS) * len(engines.MCP_PREFIXES)
