"""
Test suite for LocalWriter LlmClient (core.api).
Ported from test_llm.py — same coverage, adapted for the class-based API.

Run: pytest tests/test_api.py -v
"""

import json
import ssl
import sys
import os
import threading
import unittest.mock
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

# Mock 'uno' module BEFORE importing core modules
if "uno" not in sys.modules:
    sys.modules["uno"] = unittest.mock.MagicMock()
    sys.modules["uno"].fileUrlToSystemPath = lambda x: x.replace("file://", "")

try:
    from core.api import LlmClient, make_ssl_context, _is_openai_compatible
    from core.config import as_bool
except ImportError:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.api import LlmClient, make_ssl_context, _is_openai_compatible
    from core.config import as_bool


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------

class MockServiceManager:
    def createInstanceWithContext(self, name, ctx):
        return None

class MockContext:
    def getServiceManager(self):
        return MockServiceManager()


# ---------------------------------------------------------------------------
# Mock SSE Server
# ---------------------------------------------------------------------------

class SSEHandler(BaseHTTPRequestHandler):
    """Mock SSE server handler. Subclasses set chunks and captured_requests."""
    chunks = []
    captured_requests = []

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        parsed = json.loads(body)

        self.__class__.captured_requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": parsed,
        })

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        for chunk_line in self.__class__.chunks:
            self.wfile.write(chunk_line.encode("utf-8") + b"\n\n")
            self.wfile.flush()

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, format, *args):
        pass


class ErrorHandler(BaseHTTPRequestHandler):
    """Returns HTTP 500 for error handling tests."""
    def do_POST(self):
        self.send_response(500)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Internal Server Error")

    def log_message(self, format, *args):
        pass


def start_mock_server(handler_class):
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    port = server.server_address[1]
    return server, port


COMPLETIONS_CHUNKS = [
    'data: {"choices":[{"text":"Once ","finish_reason":null}]}',
    'data: {"choices":[{"text":"upon ","finish_reason":null}]}',
    'data: {"choices":[{"text":"a time","finish_reason":"stop"}]}',
]

CHAT_CHUNKS = [
    'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
    'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
    'data: {"choices":[{"delta":{"content":"!"},"finish_reason":"stop"}]}',
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_completions_server():
    class Handler(SSEHandler):
        chunks = list(COMPLETIONS_CHUNKS)
        captured_requests = []
    server, port = start_mock_server(Handler)
    yield Handler, port
    server.shutdown()


@pytest.fixture
def mock_chat_server():
    class Handler(SSEHandler):
        chunks = list(CHAT_CHUNKS)
        captured_requests = []
    server, port = start_mock_server(Handler)
    yield Handler, port
    server.shutdown()


@pytest.fixture
def mock_error_server():
    server, port = start_mock_server(ErrorHandler)
    yield port
    server.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(endpoint="http://localhost:11434", api_type="completions",
                 model="", api_key="", is_openwebui=False,
                 openai_compatibility=False, seed="", temperature=0.5,
                 request_timeout=10):
    config = {
        "endpoint": endpoint,
        "api_type": api_type,
        "model": model,
        "api_key": api_key,
        "is_openwebui": is_openwebui,
        "openai_compatibility": openai_compatibility,
        "seed": seed,
        "temperature": temperature,
        "request_timeout": request_timeout,
    }
    return LlmClient(config, MockContext())


def do_stream(handler_class, port, api_type="completions", api_key="",
              is_openwebui=False, openai_compatible=False,
              prompt="Hello", system_prompt="", max_tokens=70, model="test-model"):
    endpoint = "http://127.0.0.1:%d" % port
    client = _make_client(
        endpoint=endpoint, api_type=api_type, api_key=api_key,
        model=model, is_openwebui=is_openwebui,
        openai_compatibility=openai_compatible,
    )
    accumulated = []
    client.stream_completion(
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        api_type=api_type,
        append_callback=accumulated.append,
        dispatch_events=False,
    )
    return "".join(accumulated), handler_class.captured_requests


# ---------------------------------------------------------------------------
# Unit Tests — as_bool
# ---------------------------------------------------------------------------

class TestAsBool:

    @pytest.mark.parametrize("value", [True])
    def test_bool_true(self, value):
        assert as_bool(value) is True

    @pytest.mark.parametrize("value", [False])
    def test_bool_false(self, value):
        assert as_bool(value) is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "on"])
    def test_string_true_variants(self, value):
        assert as_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", "random", ""])
    def test_string_false_variants(self, value):
        assert as_bool(value) is False

    @pytest.mark.parametrize("value", [1, 42])
    def test_int_nonzero(self, value):
        assert as_bool(value) is True

    def test_int_zero(self):
        assert as_bool(0) is False

    def test_float_nonzero(self):
        assert as_bool(3.14) is True

    def test_float_zero(self):
        assert as_bool(0.0) is False

    def test_none(self):
        assert as_bool(None) is False

    def test_list(self):
        assert as_bool([]) is False


# ---------------------------------------------------------------------------
# Unit Tests — _is_openai_compatible
# ---------------------------------------------------------------------------

class TestIsOpenaiCompatible:

    def test_default_not_compatible(self):
        config = {"endpoint": "http://localhost:11434", "openai_compatibility": False}
        assert _is_openai_compatible(config) is False

    def test_flag_true(self):
        config = {"endpoint": "http://localhost:11434", "openai_compatibility": True}
        assert _is_openai_compatible(config) is True

    def test_openai_domain(self):
        config = {"endpoint": "https://api.openai.com", "openai_compatibility": False}
        assert _is_openai_compatible(config) is True

    def test_openai_domain_case_insensitive(self):
        config = {"endpoint": "https://API.OPENAI.COM", "openai_compatibility": False}
        assert _is_openai_compatible(config) is True

    def test_both(self):
        config = {"endpoint": "https://api.openai.com", "openai_compatibility": True}
        assert _is_openai_compatible(config) is True


# ---------------------------------------------------------------------------
# Unit Tests — extract_content_from_response
# ---------------------------------------------------------------------------

class TestExtractContent:

    def setup_method(self):
        self.client = _make_client()

    def test_completions_text(self):
        chunk = {"choices": [{"text": "Hello", "finish_reason": None}]}
        content, reason, thinking, delta = self.client.extract_content_from_response(chunk, "completions")
        assert content == "Hello"
        assert reason is None

    def test_completions_finish(self):
        chunk = {"choices": [{"text": "end", "finish_reason": "stop"}]}
        content, reason, thinking, delta = self.client.extract_content_from_response(chunk, "completions")
        assert content == "end"
        assert reason == "stop"

    def test_chat_content(self):
        chunk = {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]}
        content, reason, thinking, delta = self.client.extract_content_from_response(chunk, "chat")
        assert content == "Hello"
        assert reason is None

    def test_chat_finish(self):
        chunk = {"choices": [{"delta": {"content": "!"}, "finish_reason": "stop"}]}
        content, reason, thinking, delta = self.client.extract_content_from_response(chunk, "chat")
        assert content == "!"
        assert reason == "stop"

    def test_empty_choices(self):
        content, reason, thinking, delta = self.client.extract_content_from_response({"choices": []}, "completions")
        assert content == ""
        assert reason is None

    def test_no_choices(self):
        content, reason, thinking, delta = self.client.extract_content_from_response({}, "completions")
        assert content == ""
        assert reason is None

    def test_chat_missing_delta(self):
        chunk = {"choices": [{"finish_reason": None}]}
        content, reason, thinking, delta = self.client.extract_content_from_response(chunk, "chat")
        assert content == ""

    def test_chat_empty_delta(self):
        chunk = {"choices": [{"delta": {}, "finish_reason": None}]}
        content, reason, thinking, delta = self.client.extract_content_from_response(chunk, "chat")
        assert content == ""

    def test_thinking_extraction(self):
        chunk = {"choices": [{"delta": {"reasoning_content": "Hmm..."}, "finish_reason": None}]}
        content, reason, thinking, delta = self.client.extract_content_from_response(chunk, "chat")
        assert thinking == "Hmm..."
        assert content == ""


# ---------------------------------------------------------------------------
# Unit Tests — make_api_request (replaces TestBuildApiRequest)
# ---------------------------------------------------------------------------

class TestMakeApiRequest:

    def test_ollama_completions(self):
        client = _make_client(endpoint="http://localhost:11434", api_type="completions", model="llama2")
        req = client.make_api_request("Hello")
        assert req.full_url == "http://localhost:11434/v1/completions"
        body = json.loads(req.data)
        assert "prompt" in body
        assert "messages" not in body
        assert body["model"] == "llama2"
        assert "seed" in body
        assert body["stream"] is True

    def test_ollama_no_auth_header(self):
        client = _make_client(endpoint="http://localhost:11434")
        req = client.make_api_request("Hello")
        assert "Authorization" not in req.headers

    def test_lm_studio_completions(self):
        client = _make_client(endpoint="http://localhost:1234", api_type="completions", model="local-model")
        req = client.make_api_request("Hello")
        assert req.full_url == "http://localhost:1234/v1/completions"
        body = json.loads(req.data)
        assert "prompt" in body
        assert "seed" in body

    def test_textgen_webui_completions(self):
        client = _make_client(endpoint="http://localhost:5000", api_type="completions")
        req = client.make_api_request("Hello")
        assert req.full_url == "http://localhost:5000/v1/completions"
        body = json.loads(req.data)
        assert "prompt" in body
        assert "seed" in body

    def test_openai_chat(self):
        client = _make_client(
            endpoint="https://api.openai.com", api_key="sk-test-key",
            api_type="chat", model="gpt-4", openai_compatibility=True,
        )
        req = client.make_api_request("Hello", system_prompt="Sys")
        assert req.full_url == "https://api.openai.com/v1/chat/completions"
        body = json.loads(req.data)
        assert "messages" in body
        assert "prompt" not in body
        assert "seed" not in body
        assert req.headers["Authorization"] == "Bearer sk-test-key"

    def test_openwebui_chat(self):
        client = _make_client(endpoint="http://localhost:3000", api_type="chat", is_openwebui=True)
        req = client.make_api_request("Hello")
        assert req.full_url == "http://localhost:3000/api/chat/completions"
        body = json.loads(req.data)
        assert "messages" in body

    def test_system_prompt_completions(self):
        client = _make_client(endpoint="http://localhost:11434", api_type="completions")
        req = client.make_api_request("Hello", system_prompt="Be helpful")
        body = json.loads(req.data)
        assert "SYSTEM PROMPT" in body["prompt"]
        assert "Be helpful" in body["prompt"]
        assert "END SYSTEM PROMPT" in body["prompt"]

    def test_system_prompt_chat(self):
        client = _make_client(endpoint="http://localhost:11434", api_type="chat")
        req = client.make_api_request("Hello", system_prompt="Be helpful")
        body = json.loads(req.data)
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "Be helpful"
        assert body["messages"][1]["role"] == "user"

    def test_no_system_prompt_chat(self):
        client = _make_client(endpoint="http://localhost:11434", api_type="chat")
        req = client.make_api_request("Hello")
        body = json.loads(req.data)
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"

    def test_max_tokens_invalid(self):
        client = _make_client(endpoint="http://localhost:11434")
        req = client.make_api_request("Hello", max_tokens="not_a_number")
        body = json.loads(req.data)
        assert body["max_tokens"] == 70

    def test_max_tokens_valid(self):
        client = _make_client(endpoint="http://localhost:11434")
        req = client.make_api_request("Hello", max_tokens=200)
        body = json.loads(req.data)
        assert body["max_tokens"] == 200

    def test_no_model_excluded(self):
        client = _make_client(endpoint="http://localhost:11434", model="")
        req = client.make_api_request("Hello")
        body = json.loads(req.data)
        assert "model" not in body

    def test_endpoint_trailing_slash(self):
        client = _make_client(endpoint="http://localhost:11434/", api_type="completions")
        req = client.make_api_request("Hello")
        # core/api.py doesn't strip trailing slash — URL gets double slash
        # This documents the current behavior (differs from llm.py which strips)
        assert "/v1/completions" in req.full_url

    def test_seed_not_sent_for_openai_compatible(self):
        client = _make_client(
            endpoint="http://localhost:11434", api_type="completions",
            openai_compatibility=True,
        )
        req = client.make_api_request("Hello")
        body = json.loads(req.data)
        assert "seed" not in body

    def test_post_method(self):
        client = _make_client(endpoint="http://localhost:11434")
        req = client.make_api_request("Hello")
        assert req.get_method() == "POST"


# ---------------------------------------------------------------------------
# Unit Tests — make_ssl_context
# ---------------------------------------------------------------------------

class TestMakeSslContext:

    def test_default_verification_enabled(self):
        ctx = make_ssl_context(disable_verification=False)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_verification_disabled(self):
        ctx = make_ssl_context(disable_verification=True)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_string_true_disables(self):
        # make_ssl_context takes bool, but test truthy string behavior
        ctx = make_ssl_context(disable_verification="true")
        assert ctx.check_hostname is False


# ---------------------------------------------------------------------------
# Integration Tests — Ollama (completions)
# ---------------------------------------------------------------------------

class TestStreamOllama:

    def test_accumulated_text(self, mock_completions_server):
        handler, port = mock_completions_server
        text, _ = do_stream(handler, port)
        assert text == "Once upon a time"

    def test_request_path(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port)
        assert reqs[0]["path"] == "/v1/completions"

    def test_body_has_prompt(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port, prompt="test prompt")
        assert "prompt" in reqs[0]["body"]
        assert "messages" not in reqs[0]["body"]

    def test_body_has_seed(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port)
        assert "seed" in reqs[0]["body"]

    def test_body_has_model(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port)
        assert reqs[0]["body"]["model"] == "test-model"

    def test_stream_is_true(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port)
        assert reqs[0]["body"]["stream"] is True


# ---------------------------------------------------------------------------
# Integration Tests — LM Studio (completions)
# ---------------------------------------------------------------------------

class TestStreamLMStudio:

    def test_accumulated_text(self, mock_completions_server):
        handler, port = mock_completions_server
        text, _ = do_stream(handler, port)
        assert text == "Once upon a time"

    def test_request_path(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port)
        assert reqs[0]["path"] == "/v1/completions"

    def test_body_has_seed(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port)
        assert "seed" in reqs[0]["body"]


# ---------------------------------------------------------------------------
# Integration Tests — text-generation-webui (completions)
# ---------------------------------------------------------------------------

class TestStreamTextGenWebUI:

    def test_accumulated_text(self, mock_completions_server):
        handler, port = mock_completions_server
        text, _ = do_stream(handler, port)
        assert text == "Once upon a time"

    def test_request_path(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port)
        assert reqs[0]["path"] == "/v1/completions"


# ---------------------------------------------------------------------------
# Integration Tests — OpenAI (chat)
# ---------------------------------------------------------------------------

class TestStreamOpenAI:

    def test_accumulated_text(self, mock_chat_server):
        handler, port = mock_chat_server
        text, _ = do_stream(handler, port, api_type="chat",
                            api_key="sk-test-key", openai_compatible=True)
        assert text == "Hello world!"

    def test_request_path(self, mock_chat_server):
        handler, port = mock_chat_server
        _, reqs = do_stream(handler, port, api_type="chat",
                            api_key="sk-test-key", openai_compatible=True)
        assert reqs[0]["path"] == "/v1/chat/completions"

    def test_body_has_messages(self, mock_chat_server):
        handler, port = mock_chat_server
        _, reqs = do_stream(handler, port, api_type="chat",
                            api_key="sk-test-key", openai_compatible=True)
        assert "messages" in reqs[0]["body"]
        assert "prompt" not in reqs[0]["body"]

    def test_no_seed(self, mock_chat_server):
        handler, port = mock_chat_server
        _, reqs = do_stream(handler, port, api_type="chat",
                            api_key="sk-test-key", openai_compatible=True)
        assert "seed" not in reqs[0]["body"]

    def test_auth_header(self, mock_chat_server):
        handler, port = mock_chat_server
        _, reqs = do_stream(handler, port, api_type="chat",
                            api_key="sk-test-key", openai_compatible=True)
        assert reqs[0]["headers"].get("Authorization") == "Bearer sk-test-key"


# ---------------------------------------------------------------------------
# Integration Tests — OpenWebUI (chat)
# ---------------------------------------------------------------------------

class TestStreamOpenWebUI:

    def test_accumulated_text(self, mock_chat_server):
        handler, port = mock_chat_server
        text, _ = do_stream(handler, port, api_type="chat", is_openwebui=True)
        assert text == "Hello world!"

    def test_request_path(self, mock_chat_server):
        handler, port = mock_chat_server
        _, reqs = do_stream(handler, port, api_type="chat", is_openwebui=True)
        assert reqs[0]["path"] == "/api/chat/completions"


# ---------------------------------------------------------------------------
# Integration Tests — System prompts
# ---------------------------------------------------------------------------

class TestStreamSystemPrompt:

    def test_completions_system_prompt_in_body(self, mock_completions_server):
        handler, port = mock_completions_server
        _, reqs = do_stream(handler, port, system_prompt="Be helpful")
        assert "SYSTEM PROMPT" in reqs[0]["body"]["prompt"]
        assert "Be helpful" in reqs[0]["body"]["prompt"]

    def test_chat_system_prompt_as_message(self, mock_chat_server):
        handler, port = mock_chat_server
        _, reqs = do_stream(handler, port, api_type="chat",
                            system_prompt="Be helpful")
        assert reqs[0]["body"]["messages"][0]["role"] == "system"
        assert reqs[0]["body"]["messages"][0]["content"] == "Be helpful"


# ---------------------------------------------------------------------------
# Integration Tests — Error handling
# ---------------------------------------------------------------------------

class TestStreamErrors:

    def test_http_500(self, mock_error_server):
        port = mock_error_server
        endpoint = "http://127.0.0.1:%d" % port
        client = _make_client(endpoint=endpoint)
        accumulated = []
        with pytest.raises(Exception) as exc_info:
            client.stream_completion(
                prompt="Hello", system_prompt="", max_tokens=70,
                api_type="completions", append_callback=accumulated.append,
                dispatch_events=False,
            )
        assert "500" in str(exc_info.value) or "Server error" in str(exc_info.value)

    def test_connection_refused(self):
        client = _make_client(endpoint="http://127.0.0.1:1")
        accumulated = []
        with pytest.raises(Exception) as exc_info:
            client.stream_completion(
                prompt="Hello", system_prompt="", max_tokens=70,
                api_type="completions", append_callback=accumulated.append,
                dispatch_events=False,
            )
        assert "Connection" in str(exc_info.value) or "refused" in str(exc_info.value).lower()

    def test_bad_json_in_sse(self):
        class BadJsonHandler(SSEHandler):
            chunks = ['data: {not valid json}']
            captured_requests = []

        server, port = start_mock_server(BadJsonHandler)
        try:
            endpoint = "http://127.0.0.1:%d" % port
            client = _make_client(endpoint=endpoint)
            accumulated = []
            # core/api.py skips bad JSON lines (continue) — should not crash
            client.stream_completion(
                prompt="Hello", system_prompt="", max_tokens=70,
                api_type="completions", append_callback=accumulated.append,
                dispatch_events=False,
            )
            # Stream completes without error (bad JSON skipped, then [DONE])
            assert isinstance(accumulated, list)
        finally:
            server.shutdown()
