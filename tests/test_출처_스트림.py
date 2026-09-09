# -*- coding: utf-8 -*-
"""Claude Code stream-json 에서 출처를 뽑는 부분의 회귀 시험.

권한 안내 줄은 message 가 문자열이라, dict 로 알고 .get 하면 죽는다.
실제로 그렇게 터져서 출처가 통째로 사라졌다.
"""
import json

from bridgekb import engines


def _line(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def test_문자열_message_줄에_죽지_않는다():
    lines = [
        _line({"type": "system", "message": None}),
        _line({"type": "system",
               "message": "Claude requested permissions to use "
                          "mcp__bridge-guide__grade_lookup, "
                          "but you haven't granted it yet."}),
    ]
    assert engines._sources_from_stream(lines) == ([], [])


def test_도구결과에서_출처를_뽑는다():
    payload = {"found": True, "year": "2026",
               "source": {"table": "1.11", "page": 29}}
    lines = [
        _line({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1",
             "name": "mcp__bridge-guide__grade_lookup"}]}}),
        _line({"type": "system", "message": "권한 안내 같은 문자열 줄"}),
        _line({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": json.dumps(payload, ensure_ascii=False)}]}}),
    ]
    sources, used = engines._sources_from_stream(lines)
    assert sources == [{"year": "2026", "table": "1.11", "page": 29}]
    assert used == ["grade_lookup"], "화면에 무엇으로 판정했는지 보여줘야 한다"


def test_허용목록이_도구_여섯_개를_모두_덮는다():
    allowed = engines.allowed_tool_names()
    assert "mcp__bridge-guide__grade_lookup" in allowed
    assert len(allowed) == len(engines.tools.SPECS) == 6


def test_도구를_사용자_설정_없이_직접_물려_준다():
    """예전에는 사용자가 MCP를 등록해 둬야 도구가 붙었고, 안 돼 있으면
    도구 없이 답이 나왔다. 이제 서버가 호출할 때마다 직접 물려 준다."""
    cfg = json.loads(engines.mcp_config())
    server = cfg["mcpServers"]["bridge-guide"]
    assert server["command"] == "python"
    assert server["args"][0].endswith("bridge_mcp.py")
    assert engines.MCP_ENTRY.exists(), "물려 줄 MCP 진입점이 실제로 있어야 한다"
