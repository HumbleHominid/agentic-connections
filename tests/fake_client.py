"""Offline stand-in for anthropic.Anthropic that returns scripted real SDK Message objects."""

import itertools

import anthropic
import httpx2
from anthropic.types import Message

_ids = itertools.count(1)


def thinking(text=""):
    return {"type": "thinking", "thinking": text, "signature": "sig"}


def text(t):
    return {"type": "text", "text": t}


def tool(name, **inp):
    return {"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": name, "input": inp}


def msg(*content, stop_reason=None, usage=None, model="claude-haiku-5-5-test", stop_details=None):
    if stop_reason is None:
        stop_reason = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
    return Message.model_validate({
        "id": f"msg_{next(_ids)}", "type": "message", "role": "assistant", "model": model,
        "content": list(content), "stop_reason": stop_reason, "stop_sequence": None, "stop_details": stop_details,
        "usage": usage or {"input_tokens": 100, "output_tokens": 10,
                           "cache_creation_input_tokens": None, "cache_read_input_tokens": 50},
    })


def api_error(cls=anthropic.BadRequestError, message="Your credit balance is too low to access the Anthropic API.",
              status=400):
    resp = httpx2.Response(status, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    return cls(message, response=resp, body=None)


class FakeClient:
    """``script`` items are Messages to return or exceptions to raise, in order."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
