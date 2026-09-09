# -*- coding: utf-8 -*-
"""배포 경로를 지킨다 - GitHub에서 설치되고, 답은 웹에서만.

두 가지가 서로 다른 문제인데 한 번 섞어서 크게 헤맸다.

  - 터미널에서 **답하는** 것: 없애야 한다. 창마다 도구가 붙었는지가 달라서
    같은 질문에 다른 답이 나왔다.
  - GitHub에서 **설치되는** 것: 지켜야 한다. git clone 없이 어느 폴더에서든
    쓸 수 있게 하려고 공들인 부분이다.

플러그인이 화면을 열기만 하고 답하지 않으면 둘 다 만족한다. 그 경계가
`plugin.json`에 `mcpServers`가 없다는 사실 하나에 걸려 있으므로 여기서 지킨다.
"""
from __future__ import annotations

import json

from bridgekb import config

PLUGIN = config.ROOT / ".claude-plugin" / "plugin.json"
MARKET = config.ROOT / ".claude-plugin" / "marketplace.json"
COMMAND = config.ROOT / "commands" / "bridge-guide.md"


def test_깃허브에서_설치되는_매니페스트가_있다():
    """이게 없으면 /plugin marketplace add 가 통하지 않는다."""
    assert PLUGIN.exists(), "플러그인 매니페스트가 없으면 GitHub 설치가 끊긴다"
    assert MARKET.exists(), "마켓플레이스 매니페스트가 없으면 등록이 안 된다"

    market = json.loads(MARKET.read_text(encoding="utf-8"))
    assert market["plugins"][0]["name"] == "bridge-guide"


def test_플러그인이_터미널에_도구를_붙이지_않는다():
    """mcpServers를 선언하면 터미널 Claude가 도구를 쥐고 거기서 답해 버린다."""
    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
    assert "mcpServers" not in plugin, (
        "plugin.json에 mcpServers를 넣으면 터미널에서 답이 나온다. "
        "도구는 서버가 engines.mcp_config()로 직접 물려 준다.")


def test_슬래시_커맨드는_화면만_연다():
    """답을 만들지 않고 서버.py --launch 로 화면을 여는 것까지가 커맨드의 일이다."""
    body = COMMAND.read_text(encoding="utf-8")
    assert "서버.py" in body and "--launch" in body
    assert "열기.py" not in body, "지워진 파일을 부르면 커맨드가 깨진다"


def test_커맨드가_부르는_파일이_실제로_있다():
    """예전에 열기.py를 지우고 커맨드는 그대로 둬서 /bridge-guide 가 깨졌다."""
    assert (config.ROOT / "서버.py").exists()
