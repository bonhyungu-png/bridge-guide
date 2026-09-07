# -*- coding: utf-8 -*-
"""MCP 서버 진입점 - 어느 폴더에서 실행하든 돌아간다.

`python -m bridgekb mcp`는 저장소 안에서 실행해야 하지만, MCP 클라이언트
설정 파일(mcp.json, config.toml ...)은 작업 폴더를 지정하기 어렵거나
환경마다 문법이 다르다. 그래서 절대경로 하나만 적으면 되게 이 파일을 둔다:

    python C:/경로/bridge_mcp.py

의존성 없음. 파이썬 3.10 이상이면 그대로 돈다.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bridgekb.mcp_server import serve  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(serve())
