# -*- coding: utf-8 -*-
"""질문 엔진 - 웹 화면이 빌려 쓸 AI를 고르고, 같은 모양의 답을 돌려준다.

질문을 받고 답하는 곳은 웹 하나뿐이다(`서버.py`). 이 모듈은 그 서버가
"답을 만들 AI"를 어디서 빌려올지만 정한다. 바깥에 주는 모양은 하나다:

    ask(turns) -> Answer(text, sources, warning)

## 어떤 AI를 빌리나

**claude-cli** (기본)
  이미 로그인된 Claude Code 구독을 그대로 쓴다. API 키도 추가 요금도 없다.
  도구는 우리가 `--mcp-config`로 **직접 물려서** 준다 - 사용자가 MCP를
  등록해 둘 필요가 없고, 등록해 뒀더라도 `--strict-mcp-config`로 다른
  서버를 배제해 항상 같은 조건에서 답한다.

**API 엔진** (anthropic / gemini / openai)
  키가 있으면 쓸 수 있다. 도구 호출 루프를 여기서 직접 돌리므로 어떤 도구가
  무엇을 돌려줬는지 정확히 안다.

## 왜 gemini-cli · codex-cli 를 뺐나

그 CLI들은 도구 호출 내역을 돌려주지 않아서, 도구를 실제로 썼는지 확인할
방법이 없었다. 등급을 코드가 판정했는지 모델이 눈대중으로 비교했는지
구분되지 않는 답은 이 프로젝트에서 쓸 수 없다 - 그래서 지웠다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import kb, tools

TIMEOUT_SEC = 180

ROOT = Path(__file__).resolve().parent.parent
MCP_ENTRY = ROOT / "bridge_mcp.py"

# 이 호출은 이미 질의 화면 안에서 일어난 것이다. 그대로 두면 모델이 답 대신
# "GUI를 열까요?"라고 되묻는다.
EXTRA_RULES = """
이 호출은 화면에 표시할 텍스트 답을 만드는 것이다. 이미 질의 화면 안에서
물어본 것이므로 브라우저나 GUI를 열지 마라. 셸을 쓰지 말고 bridge-guide 도구만
호출해 답하라. 도구를 아끼지 말고 필요한 만큼 부르되, 답은 화면에서 읽기 좋게
짧게 쓴다.
"""


@dataclass
class Answer:
    """엔진이 무엇이든 바깥은 이 모양만 본다."""
    text: str
    sources: list = field(default_factory=list)   # [{year, table, page}]
    tools_used: list = field(default_factory=list)  # 화면에 "무엇으로 판정했는지" 보여준다
    warning: str | None = None
    engine: str = ""


class EngineError(Exception):
    """엔진이 답을 못 냈다. code는 화면이 사용자에게 보여줄 안내를 고르는 데 쓴다."""

    def __init__(self, message: str, code: str = "upstream_error"):
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------- 프롬프트

def flatten(turns: list) -> str:
    """대화를 한 덩어리 프롬프트로 만든다. CLI는 턴 목록을 받지 않는다."""
    if not turns:
        return ""
    *before, last = turns
    lines = []
    if before:
        lines.append("이전 대화:")
        for t in before:
            who = "사용자" if t.get("role") == "user" else "도우미"
            lines.append("%s: %s" % (who, str(t.get("content") or "").strip()))
        lines.append("")
        lines.append("지금 질문:")
    lines.append(str(last.get("content") or "").strip())
    return "\n".join(lines)


def system_rules() -> str:
    return tools.SYSTEM_RULES + EXTRA_RULES


# ---------------------------------------------------------------- 출처

_TABLE_IN_TEXT = re.compile(r"(20\d\d)\s*년\s*판?[^\n]{0,40}?표\s*(\d+\.\d+(?:의\d+)?)")


def page_of(year: str, table: str):
    """(연도, 표번호) -> 원본 PDF의 실제 쪽. 데이터가 유일한 근거다."""
    for rule in kb.rules(str(year)):
        if rule.get("표") == str(table) and rule.get("면"):
            return rule["면"]
    return None


def dedup(sources: list) -> list:
    """같은 (연도, 쪽)은 한 번만. 표 번호가 달라도 같은 쪽이면 그림도 하나다."""
    seen, out = set(), []
    for s in sources:
        if not s or not s.get("year") or not s.get("page"):
            continue
        key = (str(s["year"]), s["page"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"year": str(s["year"]), "table": s.get("table"), "page": s["page"]})
    return out


def sources_from_text(text: str) -> list:
    """답 텍스트에서 (연도, 표번호)를 찾고 쪽 번호는 데이터에서 조회한다.

    도구 호출 내역이 비었을 때의 폴백. 모델이 적은 면수는 믿지 않는다.
    """
    out = []
    for year, table in _TABLE_IN_TEXT.findall(text or ""):
        page = page_of(year, table)
        if page:
            out.append({"year": year, "table": table, "page": page})
    return dedup(out)


def sources_from_tool_result(name: str, payload: dict) -> list:
    """도구 하나의 결과에서 (연도, 표번호, 면)을 뽑는다.

    grade_lookup / qualitative_criteria 는 면을 필드로 주고, table_content 는
    표 마크다운 본문의 "면: N" 줄에만 갖고 있다.
    """
    if not isinstance(payload, dict) or not payload.get("found"):
        return []
    year = payload.get("year")
    if not year:
        return []

    short = name.rsplit("__", 1)[-1]
    out = []
    if short == "grade_lookup":
        src = payload.get("source") or {}
        if src.get("page"):
            out.append({"year": year, "table": src.get("table"), "page": src["page"]})
    elif short == "qualitative_criteria":
        for c in payload.get("criteria") or []:
            if c.get("page"):
                out.append({"year": year, "table": c.get("table"), "page": c["page"]})
    elif short == "table_content":
        m = re.search(r"^면:\s*(\d+)", payload.get("content") or "", re.MULTILINE)
        if m:
            out.append({"year": year, "table": payload.get("number"), "page": int(m.group(1))})
    return out


# 우리가 `--mcp-config`로 직접 물리므로 서버 이름은 항상 이것이다.
MCP_PREFIX = "mcp__bridge-guide__"


def mcp_config() -> str:
    """`claude --mcp-config`에 넘길 설정. 파일이 아니라 JSON 문자열로 준다.

    사용자가 MCP를 미리 등록해 둘 필요가 없다 - 서버가 호출할 때마다 우리
    도구를 물려 준다. 예전에는 등록을 사용자에게 맡겨서, 안 돼 있으면 도구
    없이 답이 나왔고 그걸 알아채기도 어려웠다.
    """
    return json.dumps({"mcpServers": {"bridge-guide": {
        "command": "python", "args": [str(MCP_ENTRY)]}}})


def allowed_tool_names() -> list:
    return [MCP_PREFIX + spec["name"] for spec in tools.SPECS]


# ---------------------------------------------------------------- 엔진 공통

class Engine:
    name = ""
    kind = ""          # "cli" 또는 "api"
    detail = ""

    def ask(self, turns: list) -> Answer:      # pragma: no cover - 하위에서 구현
        raise NotImplementedError


def _run(cmd: list) -> tuple[str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        raise EngineError("답이 %d초 안에 오지 않았습니다." % TIMEOUT_SEC)
    return (proc.stdout.decode("utf-8", "replace").strip(),
            proc.stderr.decode("utf-8", "replace").strip())


# ---------------------------------------------------------------- CLI 엔진

class ClaudeCli(Engine):
    """Claude Code 구독을 빌린다. 도구는 우리가 직접 물려 준다."""

    name = "claude-cli"
    kind = "cli"
    detail = "Claude Code 구독을 그대로 쓴다 (API 키 없음, 별도 설정 없음)"

    def __init__(self, exe: str):
        self.exe = exe

    def ask(self, turns: list) -> Answer:
        out, err = _run([
            self.exe, "-p", flatten(turns),
            "--output-format", "stream-json", "--verbose",
            "--strict-mcp-config", "--mcp-config", mcp_config(),
            "--allowedTools", " ".join(allowed_tool_names()),
            "--append-system-prompt", system_rules(),
        ])

        lines = out.splitlines()
        result = None
        for raw in reversed(lines):
            try:
                d = json.loads(raw.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            if d.get("type") == "result":
                result = d
                break

        if result is None:
            message = out or err or "답을 받지 못했습니다."
            code = "rate_limited" if "limit" in message.lower() else "upstream_error"
            raise EngineError(message[:400], code)
        if result.get("is_error"):
            raise EngineError(str(result.get("result") or "오류가 났습니다.")[:400])

        text = str(result.get("result") or "").strip()
        if not text:
            raise EngineError("빈 답이 돌아왔습니다.", "empty_completion")

        warning = None
        denials = result.get("permission_denials")
        if denials:
            # 도구가 막히면 등급을 코드가 판정하지 못한 채 답이 나온다 - 숨기면 안 된다.
            names = sorted({d.get("tool_name", "") for d in denials if isinstance(d, dict)})
            warning = ("허용되지 않은 도구 호출이 %d건 있었습니다(%s). 등급이 코드로 "
                       "판정되지 않았을 수 있습니다." % (len(denials), ", ".join(names)))

        sources, used = _sources_from_stream(lines)
        if not sources:
            sources = sources_from_text(text)
        if not warning and not sources and re.search(r"\b[a-e]\s*등급", text):
            # 등급을 말하면서 출처가 하나도 없다 = 도구를 안 거쳤다는 뜻이다.
            warning = ("도구 호출 내역을 찾지 못했습니다. 등급이 코드로 판정되지 "
                       "않았을 수 있습니다.")
        return Answer(text=text, sources=sources, tools_used=used,
                      warning=warning, engine=self.name)


def _sources_from_stream(lines: list) -> tuple[list, list]:
    """stream-json 줄들에서 (출처, 실제로 부른 우리 도구 이름들)을 뽑는다."""
    names, out, used = {}, [], []
    for raw in lines:
        try:
            d = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        # 권한 안내 줄은 message 가 dict 가 아니라 문자열이다. 그대로 .get 을
        # 부르면 AttributeError 로 죽어서 출처가 통째로 사라진다 - 실제로 그랬다.
        message = d.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = block.get("name") or ""
                names[block.get("id")] = name
                if name.startswith(MCP_PREFIX):
                    used.append(name[len(MCP_PREFIX):])
                continue
            if block.get("type") != "tool_result":
                continue
            name = names.get(block.get("tool_use_id")) or ""
            body = block.get("content")
            text = None
            if isinstance(body, list):
                for item in body:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text")
                        break
            elif isinstance(body, str):
                text = body
            if not text:
                continue
            try:
                out += sources_from_tool_result(name, json.loads(text))
            except (json.JSONDecodeError, ValueError):
                continue
    return dedup(out), used


# ---------------------------------------------------------------- API 엔진

MAX_TOOL_ROUNDS = 8


class ApiEngine(Engine):
    """도구 호출 루프를 직접 돈다 - 어떤 도구가 무엇을 돌려줬는지 정확히 안다."""

    kind = "api"
    env_key = ""
    default_model = ""
    model_env = ""
    detail_base = ""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = os.environ.get(self.model_env) or self.default_model
        self.detail = "%s (모델 %s, %s 로 바꿀 수 있음)" % (
            self.detail_base, self.model, self.model_env)


class AnthropicApi(ApiEngine):
    name = "anthropic-api"
    env_key = "ANTHROPIC_API_KEY"
    model_env = "BRIDGE_GUIDE_ANTHROPIC_MODEL"
    default_model = "claude-sonnet-5"
    detail_base = "Anthropic API 키로 직접 호출"

    def ask(self, turns: list) -> Answer:
        import anthropic   # 키를 쓸 때만 필요하다

        client = anthropic.Anthropic(api_key=self.api_key)
        schema = [{"name": s["name"], "description": s["description"],
                   "input_schema": s["inputSchema"]} for s in tools.SPECS]
        messages = [{"role": t.get("role", "user"), "content": str(t.get("content") or "")}
                    for t in turns]
        collected, used = [], []

        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.messages.create(
                model=self.model, max_tokens=4096,
                system=system_rules(), tools=schema, messages=messages)
            calls = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if not calls:
                text = "".join(getattr(b, "text", "") for b in resp.content).strip()
                if not text:
                    raise EngineError("빈 답이 돌아왔습니다.", "empty_completion")
                return Answer(text=text, sources=dedup(collected),
                              tools_used=used, engine=self.name)

            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for call in calls:
                payload = _safe_call(call.name, dict(call.input))
                used.append(call.name.rsplit('__', 1)[-1])
                collected += sources_from_tool_result(call.name, payload)
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": json.dumps(payload, ensure_ascii=False)})
            messages.append({"role": "user", "content": results})

        raise EngineError("도구 호출이 %d번을 넘었습니다." % MAX_TOOL_ROUNDS)


class GeminiApi(ApiEngine):
    name = "gemini-api"
    env_key = "GEMINI_API_KEY"
    model_env = "BRIDGE_GUIDE_GEMINI_MODEL"
    default_model = "gemini-2.5-flash"
    detail_base = "Google Gemini API 키로 직접 호출"

    def ask(self, turns: list) -> Answer:
        from google import genai              # pip install google-genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        declarations = [types.FunctionDeclaration(
            name=s["name"], description=s["description"],
            parameters=s["inputSchema"]) for s in tools.SPECS]
        config = types.GenerateContentConfig(
            system_instruction=system_rules(),
            tools=[types.Tool(function_declarations=declarations)])

        contents = [types.Content(
            role="user" if t.get("role") != "assistant" else "model",
            parts=[types.Part(text=str(t.get("content") or ""))]) for t in turns]
        collected, used = [], []

        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.models.generate_content(
                model=self.model, contents=contents, config=config)
            calls = list(resp.function_calls or [])
            if not calls:
                text = (resp.text or "").strip()
                if not text:
                    raise EngineError("빈 답이 돌아왔습니다.", "empty_completion")
                return Answer(text=text, sources=dedup(collected),
                              tools_used=used, engine=self.name)

            contents.append(resp.candidates[0].content)
            parts = []
            for call in calls:
                payload = _safe_call(call.name, dict(call.args or {}))
                used.append(call.name.rsplit('__', 1)[-1])
                collected += sources_from_tool_result(call.name, payload)
                parts.append(types.Part.from_function_response(
                    name=call.name, response={"result": payload}))
            contents.append(types.Content(role="user", parts=parts))

        raise EngineError("도구 호출이 %d번을 넘었습니다." % MAX_TOOL_ROUNDS)


class OpenAiApi(ApiEngine):
    name = "openai-api"
    env_key = "OPENAI_API_KEY"
    model_env = "BRIDGE_GUIDE_OPENAI_MODEL"
    default_model = "gpt-4.1"
    detail_base = "OpenAI API 키로 직접 호출"

    def ask(self, turns: list) -> Answer:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        schema = [{"type": "function", "function": {
            "name": s["name"], "description": s["description"],
            "parameters": s["inputSchema"]}} for s in tools.SPECS]
        messages = [{"role": "system", "content": system_rules()}]
        messages += [{"role": t.get("role", "user"), "content": str(t.get("content") or "")}
                     for t in turns]
        collected, used = [], []

        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=self.model, messages=messages, tools=schema)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                text = (msg.content or "").strip()
                if not text:
                    raise EngineError("빈 답이 돌아왔습니다.", "empty_completion")
                return Answer(text=text, sources=dedup(collected),
                              tools_used=used, engine=self.name)

            messages.append(msg)
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except (json.JSONDecodeError, ValueError):
                    args = {}
                payload = _safe_call(call.function.name, args)
                used.append(call.function.name.rsplit('__', 1)[-1])
                collected += sources_from_tool_result(call.function.name, payload)
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(payload, ensure_ascii=False)})

        raise EngineError("도구 호출이 %d번을 넘었습니다." % MAX_TOOL_ROUNDS)


def _safe_call(name: str, arguments: dict) -> dict:
    """도구 실행. 실패해도 루프를 죽이지 않고 모델에게 사실대로 알린다."""
    try:
        return tools.call(name.rsplit("__", 1)[-1], arguments)
    except Exception as exc:                       # noqa: BLE001 - 모델에게 전달한다
        return {"found": False, "error": "%s: %s" % (type(exc).__name__, exc)}


# ---------------------------------------------------------------- 선택

# 앞쪽이 우선. CLI가 먼저인 이유는 이미 낸 구독을 그대로 쓰기 때문이다
# (API 엔진은 키에 요금이 붙는다).
_API_ENGINES = [AnthropicApi, GeminiApi, OpenAiApi]


def available() -> list[Engine]:
    """지금 이 컴퓨터에서 실제로 쓸 수 있는 엔진들. 우선순위 순."""
    found = []
    path = shutil.which("claude")
    if path:
        found.append(ClaudeCli(path))
    for cls in _API_ENGINES:
        key = os.environ.get(cls.env_key)
        if key:
            found.append(cls(key))
    return found


def pick(name: str | None = None) -> Engine | None:
    """엔진 하나를 고른다. 이름이 없으면 환경변수, 그것도 없으면 우선순위."""
    wanted = name or os.environ.get("BRIDGE_GUIDE_ENGINE")
    engines = available()
    if wanted:
        for e in engines:
            if e.name == wanted:
                return e
        return None
    return engines[0] if engines else None


def ask(turns: list, engine: str | None = None) -> Answer:
    """이 모듈의 유일한 바깥 창구."""
    picked = pick(engine)
    if picked is None:
        raise EngineError(
            "쓸 수 있는 AI가 없습니다. Claude Code를 설치해 로그인하거나 "
            "ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY 중 하나를 넣어 주세요.",
            "no_engine")
    if not flatten(turns).strip():
        raise EngineError("질문이 비었습니다.", "empty_completion")
    return picked.ask(turns)
