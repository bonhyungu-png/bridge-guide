"""MCP 서버 (stdio) - 빌려 온 AI에게 우리 도구를 건네는 내부 통로.

왜 MCP인가: 웹 화면이 답을 만들려면 AI가 필요한데, 그 AI에게 우리 도구를
쥐여 줄 표준 통로가 MCP다. 사용자가 이미 쓰는 Claude Code 구독을 그대로
빌리면서도 등급 판정은 우리 코드가 하게 만드는 것이 목적이다.

**의존성이 없다.** MCP stdio 전송은 줄바꿈으로 구분된 JSON-RPC 2.0일 뿐이라
표준 라이브러리만으로 구현했다. `pip install` 없이 파이썬만 있으면 돈다 -
이 프로젝트가 자체완결이어야 하는 이유와 같다.

사용자가 등록할 것은 없다. `서버.py`가 AI를 부를 때마다
`claude --mcp-config`로 이 서버를 직접 물려 준다(`engines.mcp_config()`).
직접 띄워 보려면:

    python bridge_mcp.py

주의: stdout은 프로토콜 전용이다. 진단 출력은 전부 stderr로 보낸다.
"""
from __future__ import annotations

import json
import sys
import traceback

from . import __version__, config, tools

# 우리가 말할 줄 아는 프로토콜 판본들. 클라이언트가 요청한 판본을 알면
# 그대로 되돌려 주고, 모르면 우리 최신 판본을 제시한다(그쪽이 맞춰준다).
LATEST_PROTOCOL = "2025-06-18"
KNOWN_PROTOCOLS = {"2024-11-05", "2025-03-26", LATEST_PROTOCOL}

SERVER_INFO = {"name": "bridge-guide", "title": "교량 지침서 가이드",
               "version": __version__}

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _write(message: dict) -> None:
    """JSON-RPC 메시지 한 줄을 stdout에 쓴다.

    바이트로 직접 쓰는 이유: 윈도우 텍스트 모드는 "\\n"을 "\\r\\n"으로 바꾸고
    콘솔 기본 인코딩이 cp949라 한글이 깨진다. 둘 다 프로토콜을 망가뜨린다.
    """
    data = json.dumps(message, ensure_ascii=False, default=str)
    sys.stdout.buffer.write(data.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _log(*parts) -> None:
    print(*parts, file=sys.stderr, flush=True)


def _result(req_id, result: dict) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str) -> None:
    _write({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


# ---------------- 메서드 ----------------

def _initialize(params: dict) -> dict:
    asked = params.get("protocolVersion")
    version = asked if asked in KNOWN_PROTOCOLS else LATEST_PROTOCOL
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        # 서버가 모델에게 거는 행동 지침. 등급을 직접 계산하지 말라는
        # 절대 규칙이 여기 실려 나간다.
        "instructions": tools.SYSTEM_RULES,
    }


def _tools_list(_params: dict) -> dict:
    return {"tools": tools.descriptors()}


def _tools_call(params: dict) -> dict:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if name not in tools.BY_NAME:
        # 프로토콜 오류가 아니라 도구 실행 오류다 - 모델이 보고 고쳐 쓸 수 있게
        # isError로 돌려준다.
        return _tool_error("그런 도구가 없습니다: %s (있는 것: %s)"
                           % (name, ", ".join(tools.BY_NAME)))
    try:
        result = tools.call(name, arguments)
    except TypeError as e:
        return _tool_error("인자가 맞지 않습니다: %s" % e)
    except ValueError as e:
        return _tool_error(str(e))
    except Exception:
        _log(traceback.format_exc())
        return _tool_error("도구 실행 중 오류가 났습니다.")

    return {
        "content": [{"type": "text",
                     "text": json.dumps(result, ensure_ascii=False, indent=2, default=str)}],
        "isError": False,
    }


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


HANDLERS = {
    "initialize": _initialize,
    "tools/list": _tools_list,
    "tools/call": _tools_call,
    "ping": lambda _params: {},
}


def handle(message: dict) -> None:
    """요청 하나를 처리한다. 알림(id 없음)에는 응답하지 않는다."""
    req_id = message.get("id")
    method = message.get("method")

    if method is None:  # 응답 메시지. 우리는 요청을 보내지 않으므로 무시한다.
        return
    if req_id is None:  # 알림 - notifications/initialized 등. 조용히 받는다.
        return

    handler = HANDLERS.get(method)
    if handler is None:
        _error(req_id, METHOD_NOT_FOUND, "지원하지 않는 메서드: %s" % method)
        return

    try:
        _result(req_id, handler(message.get("params") or {}))
    except Exception:
        _log(traceback.format_exc())
        _error(req_id, INTERNAL_ERROR, "서버 내부 오류")


def serve() -> int:
    years = config.available_years()
    if not years:
        _log("경고: 정본 데이터를 찾지 못했습니다 - %s" % config.DATA_ROOT)
    else:
        _log("bridge-guide MCP 서버 시작. 판본: %s" % ", ".join(years))

    for raw in sys.stdin.buffer:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            _error(None, PARSE_ERROR, "JSON을 읽지 못했습니다: %s" % e)
            continue
        if isinstance(message, list):  # 배치 요청
            for item in message:
                if isinstance(item, dict):
                    handle(item)
        elif isinstance(message, dict):
            handle(message)
        else:
            _error(None, INVALID_REQUEST, "요청 형식이 아닙니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
