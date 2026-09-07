"""MCP 서버 - 실제 클라이언트처럼 stdio로 붙어서 프로토콜을 확인한다.

함수를 직접 부르지 않고 서브프로세스를 띄우는 이유: 이 서버가 깨지는 자리는
로직이 아니라 **경계**다. 윈도우 콘솔이 개행을 \\r\\n으로 바꾸거나 cp949로
한글을 못 찍으면 프로토콜 자체가 무너지는데, 함수 호출로는 그게 안 잡힌다.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from bridgekb import config

pytestmark = pytest.mark.skipif(
    not config.DATA_DIR.exists(), reason="정본 데이터 없음")

ROOT = config.ROOT

HELLO = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"}}}
READY = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def talk(*requests) -> dict:
    """요청들을 서버에 흘려보내고 {id: 응답}을 돌려준다."""
    payload = b"".join(
        json.dumps(r, ensure_ascii=False).encode("utf-8") + b"\n" for r in requests)
    proc = subprocess.run([sys.executable, "-m", "bridgekb", "mcp"],
                          cwd=ROOT, input=payload,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")

    out = {}
    for line in proc.stdout.splitlines():
        msg = json.loads(line.decode("utf-8"))
        out[msg.get("id")] = msg
    return out


def call(name, arguments=None, req_id=9):
    return {"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}}}


def payload_of(msg) -> dict:
    """tools/call 응답 안의 JSON 본문을 꺼낸다."""
    return json.loads(msg["result"]["content"][0]["text"])


def test_핸드셰이크가_성립한다():
    res = talk(HELLO, READY)[1]["result"]
    assert res["protocolVersion"] == "2025-06-18"
    assert res["serverInfo"]["name"] == "bridge-guide"
    assert "tools" in res["capabilities"]


def test_모르는_프로토콜을_요청하면_우리_판본을_제시한다():
    hello = dict(HELLO, params=dict(HELLO["params"], protocolVersion="1999-01-01"))
    assert talk(hello)[1]["result"]["protocolVersion"] == "2025-06-18"


def test_서버지시문에_등급을_직접_계산하지_말라는_규칙이_실려간다():
    """이 규칙이 빠지면 모델이 스스로 수치를 비교한다 - 이 프로젝트가 막으려는 것."""
    instructions = talk(HELLO)[1]["result"]["instructions"]
    assert "grade_lookup" in instructions
    assert "직접 비교하는 것은 금지" in instructions


def test_도구_여섯_개를_노출한다():
    msgs = talk(HELLO, READY, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = [t["name"] for t in msgs[2]["result"]["tools"]]
    assert names == ["list_members", "grade_lookup", "qualitative_criteria",
                     "table_lookup", "table_content", "body_search"]


def test_등급판정이_stdio를_건너와도_그대로다():
    msgs = talk(HELLO, READY, call("grade_lookup", {
        "member": "콘크리트 바닥판", "indicator": "균열폭", "value": 0.25}))
    body = payload_of(msgs[9])
    assert body["grade"] == "b"
    assert body["quote"].startswith("균열폭"), "한글이 깨지면 여기서 드러난다"
    assert body["source"] == {"table": "1.11", "page": "1-27"}


def test_알림에는_응답하지_않는다():
    msgs = talk(HELLO, READY)
    assert set(msgs) == {1}, "id 없는 알림에 응답하면 클라이언트가 혼란스러워한다"


def test_없는_도구는_프로토콜_오류가_아니라_isError로_돌려준다():
    """모델이 결과를 보고 스스로 고쳐 부를 수 있어야 한다."""
    msgs = talk(HELLO, READY, call("없는도구"))
    assert "error" not in msgs[9]
    assert msgs[9]["result"]["isError"] is True


def test_인자가_모자라면_isError로_알려준다():
    msgs = talk(HELLO, READY, call("grade_lookup", {"member": "콘크리트 바닥판"}))
    assert msgs[9]["result"]["isError"] is True


def test_없는_메서드는_JSONRPC_오류다():
    msgs = talk(HELLO, {"jsonrpc": "2.0", "id": 3, "method": "없는메서드", "params": {}})
    assert msgs[3]["error"]["code"] == -32601


def test_깨진_JSON에도_서버가_죽지_않는다():
    payload = (b'{ this is not json\n'
               + json.dumps(HELLO, ensure_ascii=False).encode("utf-8") + b"\n")
    proc = subprocess.run([sys.executable, "-m", "bridgekb", "mcp"],
                          cwd=ROOT, input=payload,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    assert proc.returncode == 0
    ids = [json.loads(line.decode("utf-8")).get("id") for line in proc.stdout.splitlines()]
    assert 1 in ids, "앞줄이 깨졌다고 뒤 요청까지 버리면 안 된다"


def test_stdout에는_프로토콜_외의_것이_섞이지_않는다():
    """진단 문구가 stdout에 새면 클라이언트가 파싱에 실패한다."""
    proc = subprocess.run([sys.executable, "-m", "bridgekb", "mcp"],
                          cwd=ROOT,
                          input=json.dumps(HELLO).encode("utf-8") + b"\n",
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    for line in proc.stdout.splitlines():
        json.loads(line.decode("utf-8"))  # 한 줄이라도 JSON이 아니면 여기서 터진다
    assert b"\r\n" not in proc.stdout, "윈도우 개행이 섞이면 메시지 경계가 흔들린다"
