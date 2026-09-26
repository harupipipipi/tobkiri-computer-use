from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import time
import pytest

from tobkiri_computer_use.transport import McpTransport,ComputerError

COMMAND=[sys.executable,str(Path(__file__).parent/'fixtures/fake_mcp.py')]


def test_out_of_order_responses_are_delivered_to_correct_callers():
    with McpTransport(COMMAND) as t, ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(t.request,"echo",{"value":i,"delay":(8-i)*.02}) for i in range(8)]
        assert [f.result()["echo"] for f in futures] == list(range(8))
        assert not t._pending


def test_timeout_late_reply_does_not_poison_next_request():
    with McpTransport(COMMAND) as t:
        with pytest.raises(ComputerError) as exc:
            t.request("echo",{"value":"late","delay":.1},timeout=.01)
        assert exc.value.code=="timeout"
        assert t.request("echo",{"value":"new","delay":.2})["echo"]=="new"
        assert not t._pending


def test_tool_errors_are_raised():
    with McpTransport(COMMAND) as t:
        with pytest.raises(ComputerError,match="intentional failure"):
            t.call("test")


def test_disconnect_wakes_pending_request():
    with McpTransport(COMMAND) as t, ThreadPoolExecutor() as pool:
        pending=pool.submit(t.request,"hang")
        time.sleep(.03)
        t.proc.terminate()
        with pytest.raises(ComputerError) as exc: pending.result(timeout=2)
        assert exc.value.code=="transport_closed"
