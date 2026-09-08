# -*- coding: utf-8 -*-
"""API 키만 있을 때 - 도구 호출 루프를 직접 돌리는 가장 짧은 예제.

MCP도 CLI도 없이 "그냥 API로" 쓰고 싶을 때 무엇을 붙여야 하는지 보여준다.
핵심은 **모델에게 도구를 쥐여 주는 것**이다. 등급은 모델이 눈대중으로 정하는
게 아니라 `bridgekb.tools.grade_lookup` 이 판정규칙표를 대조해 계산한다.

    pip install anthropic          # 또는 google-genai / openai
    set ANTHROPIC_API_KEY=...      # (리눅스·맥은 export)
    python examples/api_직접호출.py "콘크리트 바닥판 균열폭 0.25mm면 몇 등급이야?"

붙일 것은 세 가지뿐이다:

    1. 시스템 프롬프트  bridgekb.tools.SYSTEM_RULES
    2. 도구 명세        bridgekb.tools.SPECS  (name / description / inputSchema)
    3. 도구 실행        bridgekb.tools.call(name, arguments)

아래는 그 셋을 공급사 형식으로 옮기는 30줄이다. 실제로는 이 저장소의
`bridgekb/engines.py` 가 세 공급사(Anthropic·Gemini·OpenAI)를 모두 처리하므로,
그냥 쓰고 싶으면 이 파일 대신 이렇게 하면 된다:

    python -m bridgekb ask "콘크리트 바닥판 균열폭 0.25mm면 몇 등급이야?"
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bridgekb import tools  # noqa: E402


def ask_anthropic(question: str, model: str = "claude-sonnet-5") -> str:
    import anthropic

    client = anthropic.Anthropic()          # ANTHROPIC_API_KEY 를 읽는다

    # 1) 우리 도구 명세를 Anthropic 형식으로 옮긴다. 이름·설명은 그대로 쓴다.
    schema = [{"name": s["name"],
               "description": s["description"],
               "input_schema": s["inputSchema"]} for s in tools.SPECS]

    messages = [{"role": "user", "content": question}]

    while True:
        resp = client.messages.create(
            model=model, max_tokens=2048,
            system=tools.SYSTEM_RULES,      # 2) 등급을 직접 계산하지 말라는 규칙
            tools=schema, messages=messages)

        calls = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
        if not calls:
            return "".join(getattr(b, "text", "") for b in resp.content).strip()

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for call in calls:
            # 3) 도구를 실제로 실행한다 - 여기가 등급이 정해지는 유일한 자리다.
            payload = tools.call(call.name, dict(call.input))
            print("  [도구] %s -> %s" % (call.name, json.dumps(payload, ensure_ascii=False)[:90]))
            results.append({"type": "tool_result", "tool_use_id": call.id,
                            "content": json.dumps(payload, ensure_ascii=False)})
        messages.append({"role": "user", "content": results})


def main() -> int:
    question = " ".join(sys.argv[1:]) or "콘크리트 바닥판 균열폭 0.25mm면 몇 등급이야?"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    print("질문:", question)
    try:
        print(ask_anthropic(question))
    except ImportError:
        print("anthropic 패키지가 없습니다: pip install anthropic")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
