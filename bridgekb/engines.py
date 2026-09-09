# -*- coding: utf-8 -*-
"""질문 엔진 - 어떤 AI로 묻든 같은 규칙, 같은 도구, 같은 모양의 답을 받는다.

이 저장소의 조회 엔진(`bridgekb`)은 AI를 모른다. 등급은 파이썬이 판정하고
AI는 그 결과를 문장으로 옮길 뿐이다. 그런데 그 "AI를 부르는 방법"은 사람마다
다르다 - Claude Code를 쓰는 사람, Gemini CLI를 쓰는 사람, API 키만 있는 사람.

그래서 부르는 방법을 여기 한 곳에 모으고, 바깥(서버·CLI)에는 하나의 모양만 준다:

    ask(turns) -> Answer(text, sources, warning)

## 두 갈래

**CLI 엔진** (`claude` `gemini` `codex`)
  이미 로그인된 구독을 그대로 쓴다. API 키도, 추가 요금도 없다.
  도구는 그 CLI에 등록된 MCP 서버(bridge_mcp.py)가 제공한다 - 등록이
  안 돼 있으면 도구 없이 답하게 되므로, 그 경우를 감지해 경고를 붙인다.

**API 엔진** (anthropic / gemini / openai)
  키가 있으면 이쪽을 쓸 수 있다. 도구 호출 루프를 **여기서 직접 돌리므로**
  어떤 도구가 무엇을 돌려줬는지 정확히 안다 - 출처가 가장 정확한 경로다.

## 출처를 얻는 방법이 엔진마다 다르다

답 아래에 원본 PDF 쪽을 띄우려면 (연도, 표번호, 면)이 필요하다.

  - API 엔진, claude CLI: 도구 호출 결과에서 그대로 뽑는다 (정확)
  - gemini/codex CLI: 도구 내역을 볼 수 없으므로 답 텍스트에서 표 번호를
    찾고, 면은 모델 말이 아니라 **우리 데이터에서** 조회한다 (모델이 면수를
    잘못 적어도 올바른 쪽이 나온다)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from . import kb, tools

TIMEOUT_SEC = 180

# 웹 화면 안에서 부를 때 붙이는 규칙. SKILL.md의 0단계("먼저 GUI를 연다")가
# 여기서는 이미 GUI 안이라 무의미하고, 그대로 두면 답 대신 승인 요청이 온다.
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
    """대화를 한 덩어리 프롬프트로 만든다. CLI들은 턴 목록을 받지 않는다."""
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

_TABLE_IN_TEXT = re.compile(r"(20\d\d)\s*년판[^\n]{0,40}?표\s*(\d+\.\d+(?:의\d+)?)")


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

    도구 호출 내역을 볼 수 없는 엔진용 폴백. 모델이 적은 면수는 믿지 않는다.
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

    short = name.rsplit("__", 1)[-1]   # mcp__bridge-guide__grade_lookup 도 받는다
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


# MCP 도구 이름은 이 도구를 "어떻게 붙였는지"에 따라 달라진다. 같은 grade_lookup 인데
#   프로젝트 .mcp.json / claude mcp add  ->  mcp__bridge-guide__grade_lookup
#   플러그인 설치                        ->  mcp__plugin_bridge-guide_bridge-guide__grade_lookup
# 예전에는 앞의 것만 --allowedTools 에 넣어서, 플러그인으로 설치한 컴퓨터에서는
# 도구가 통째로 권한 거부됐다(permission_denials). 답은 나오는데 등급을 코드가
# 판정하지 못하고 출처도 비는 상태였다. 그래서 알려진 접두사를 전부 넣는다.
MCP_PREFIXES = (
    "mcp__bridge-guide__",
    "mcp__plugin_bridge-guide_bridge-guide__",
)


def allowed_tool_names() -> list:
    """--allowedTools 에 넘길 이름들. 붙인 방식이 무엇이든 걸리도록 전부 준다."""
    return [prefix + spec["name"]
            for prefix in MCP_PREFIXES
            for spec in tools.SPECS]


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


def _plain_text_answer(out: str, err: str, engine: str) -> Answer:
    """도구 내역을 볼 수 없는 CLI들의 공통 마무리 - 텍스트에서 출처를 되찾는다."""
    text = out or err
    if not text:
        raise EngineError("빈 답이 돌아왔습니다.", "empty_completion")
    if "limit" in text.lower() and len(text) < 400:
        raise EngineError(text[:400], "rate_limited")

    sources = sources_from_text(text)
    warning = None
    if not sources and re.search(r"\b[a-e]\s*등급", text):
        warning = ("도구를 썼는지 확인할 수 없었습니다. "
                   "bridge_mcp.py 를 이 도구에 MCP로 등록했는지 확인하세요.")
    return Answer(text=text, sources=sources, warning=warning, engine=engine)


# ---------------------------------------------------------------- CLI 엔진

class ClaudeCli(Engine):
    """Claude Code. 유일하게 도구 호출 내역(stream-json)을 그대로 볼 수 있다."""

    name = "claude-cli"
    kind = "cli"
    detail = "Claude Code 구독을 그대로 쓴다 (API 키 없음)"

    def __init__(self, exe: str):
        self.exe = exe

    def ask(self, turns: list) -> Answer:
        allowed = allowed_tool_names()
        out, err = _run([
            self.exe, "-p", flatten(turns),
            "--output-format", "stream-json", "--verbose",
            "--allowedTools", " ".join(allowed),
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

        sources = _sources_from_stream(lines) or sources_from_text(text)
        if not warning and not sources and re.search(r"\b[a-e]\s*등급", text):
            # 등급을 말하면서 출처가 하나도 없다 = 도구를 안 거쳤다는 뜻이다.
            # 예전에 이 경우가 아무 표시 없이 지나가서 원인을 늦게 찾았다.
            warning = ("도구 호출 내역을 찾지 못했습니다. bridge-guide 가 이 컴퓨터에 "
                       "MCP로 붙어 있는지 확인하세요(claude mcp list).")
        return Answer(text=text, sources=sources, warning=warning, engine=self.name)


def _sources_from_stream(lines: list) -> list:
    """stream-json 줄들에서 tool_use 이름과 tool_result 내용을 짝지어 읽는다."""
    names, out = {}, []
    for raw in lines:
        try:
            d = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        # 권한 안내 줄은 message 가 dict 가 아니라 문자열이다("...but you haven't
        # granted it yet."). 그대로 .get 을 부르면 AttributeError 로 죽어서 출처가
        # 통째로 사라진다 - 실제로 그렇게 터졌다. 모양이 다른 줄은 건너뛴다.
        message = d.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                names[block.get("id")] = block.get("name")
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
    return dedup(out)


class GeminiCli(Engine):
    name = "gemini-cli"
    kind = "cli"
    detail = "Gemini CLI 로그인을 그대로 쓴다 (MCP 등록 필요)"

    def __init__(self, exe: str):
        self.exe = exe

    def ask(self, turns: list) -> Answer:
        prompt = system_rules() + "\n\n---\n\n" + flatten(turns)
        return _plain_text_answer(*_run([self.exe, "-p", prompt]), engine=self.name)


class CodexCli(Engine):
    name = "codex-cli"
    kind = "cli"
    detail = "Codex CLI 로그인을 그대로 쓴다 (MCP 등록 필요)"

    def __init__(self, exe: str):
        self.exe = exe

    def ask(self, turns: list) -> Answer:
        prompt = system_rules() + "\n\n---\n\n" + flatten(turns)
        return _plain_text_answer(
            *_run([self.exe, "exec", "--skip-git-repo-check", prompt]), engine=self.name)


# ---------------------------------------------------------------- API 엔진

MAX_TOOL_ROUNDS = 8


class ApiEngine(Engine):
    """도구 호출 루프를 직접 돈다 - 어떤 도구가 무엇을 돌려줬는지 정확히 안다."""

    kind = "api"
    env_key = ""
    default_model = ""
    model_env = ""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = os.environ.get(self.model_env) or self.default_model
        self.detail = "%s (모델 %s, %s 로 바꿀 수 있음)" % (
            self.detail_base, self.model, self.model_env)

    detail_base = ""


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
        collected = []

        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.messages.create(
                model=self.model, max_tokens=4096,
                system=system_rules(), tools=schema, messages=messages)
            calls = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if not calls:
                text = "".join(getattr(b, "text", "") for b in resp.content).strip()
                if not text:
                    raise EngineError("빈 답이 돌아왔습니다.", "empty_completion")
                return Answer(text=text, sources=dedup(collected), engine=self.name)

            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for call in calls:
                payload = _safe_call(call.name, dict(call.input))
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
        collected = []

        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.models.generate_content(
                model=self.model, contents=contents, config=config)
            calls = list(resp.function_calls or [])
            if not calls:
                text = (resp.text or "").strip()
                if not text:
                    raise EngineError("빈 답이 돌아왔습니다.", "empty_completion")
                return Answer(text=text, sources=dedup(collected), engine=self.name)

            contents.append(resp.candidates[0].content)
            parts = []
            for call in calls:
                payload = _safe_call(call.name, dict(call.args or {}))
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
        collected = []

        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=self.model, messages=messages, tools=schema)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                text = (msg.content or "").strip()
                if not text:
                    raise EngineError("빈 답이 돌아왔습니다.", "empty_completion")
                return Answer(text=text, sources=dedup(collected), engine=self.name)

            messages.append(msg)
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except (json.JSONDecodeError, ValueError):
                    args = {}
                payload = _safe_call(call.function.name, args)
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
_CLI_ENGINES = [("claude", ClaudeCli), ("gemini", GeminiCli), ("codex", CodexCli)]
_API_ENGINES = [AnthropicApi, GeminiApi, OpenAiApi]


def available() -> list[Engine]:
    """지금 이 컴퓨터에서 실제로 쓸 수 있는 엔진들. 우선순위 순."""
    found = []
    for exe, cls in _CLI_ENGINES:
        path = shutil.which(exe)
        if path:
            found.append(cls(path))
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
            "쓸 수 있는 AI가 없습니다. claude/gemini/codex 중 하나를 설치하거나 "
            "ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY 중 하나를 넣어 주세요.",
            "no_engine")
    if not flatten(turns).strip():
        raise EngineError("질문이 비었습니다.", "empty_completion")
    return picked.ask(turns)
