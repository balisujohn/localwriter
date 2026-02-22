"""
LLM API client for LocalWriter.
Takes a config dict (from core.config.get_api_config) and UNO ctx.
"""
import json
import ssl
import urllib.request

from .streaming_deltas import accumulate_delta

from core.logging import log_to_file, debug_log, update_activity_state

# Set True to call toolkit.processEventsToIdle() when stream chunks arrive (refreshes UI;
# can cause hangs on some systems). Leave code in place, toggle when needed.
PROCESS_EVENTS_DURING_STREAM = True


def format_error_message(e):
    """Map common exceptions to user-friendly advice."""
    import socket
    import urllib.error

    msg = str(e)
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 401:
            return "Invalid API Key. Please check your settings."
        if e.code == 403:
            return "API access Forbidden. Your key may lack permissions for this model."
        if e.code == 404:
            return "Endpoint not found (404). Check your URL and Model name."
        if e.code >= 500:
            return "Server error (%d). The AI provider is having issues." % e.code
        return "HTTP Error %d: %s" % (e.code, e.reason)

    if isinstance(e, urllib.error.URLError):
        reason = str(e.reason)
        if "Connection refused" in reason or "111" in reason:
            return "Connection Refused. Is your local AI server (Ollama/LM Studio) running?"
        if "getaddrinfo failed" in reason:
            return "DNS Error. Could not resolve the endpoint URL."
        return "Connection Error: %s" % reason

    if isinstance(e, socket.timeout) or "timed out" in msg.lower():
        return "Request Timed Out. Try increasing 'Request Timeout' in Settings."

    return msg


def format_error_for_display(e):
    """Return user-friendly error string for display in cells or dialogs."""
    return "Error: %s" % format_error_message(e)


def make_ssl_context(disable_verification=False):
    """Create an SSL context. Optionally disables certificate verification."""
    if disable_verification:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
    return ssl.create_default_context()


def _extract_thinking_from_delta(chunk_delta):
    """Extract reasoning/thinking text from a stream delta for display in UI."""
    for field in ["reasoning_content", "thought", "thinking"]:
        thinking = chunk_delta.get(field)
        if isinstance(thinking, str) and thinking:
            return thinking

    details = chunk_delta.get("reasoning_details")
    if isinstance(details, list):
        parts = []
        for item in details:
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type in ("reasoning.text", "thought", "reasoning"):
                    parts.append(item.get("text") or "")
                elif item_type == "reasoning.summary":
                    parts.append(item.get("summary") or "")
        if parts:
            return "".join(parts)

    return ""


def _normalize_message_content(raw):
    """Return a single string from API message content (string or list of parts)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text") or "")
                elif "text" in item:
                    parts.append(item.get("text") or "")
        return "".join(parts) if parts else None
    return str(raw)


def _is_openai_compatible(config):
    endpoint = config.get("endpoint", "")
    return config.get("openai_compatibility", False) or (
        "api.openai.com" in endpoint.lower()
    )


class LlmClient:
    """LLM API client. Takes config dict from get_api_config(ctx) and UNO ctx."""

    def __init__(self, config, ctx):
        self.config = config
        self.ctx = ctx

    def _endpoint(self):
        return self.config.get("endpoint", "http://127.0.0.1:5000")

    def _api_path(self):
        return "/api" if self.config.get("is_openwebui") else "/v1"

    def _headers(self):
        h = {"Content-Type": "application/json"}
        api_key = self.config.get("api_key", "")
        if api_key:
            h["Authorization"] = "Bearer %s" % api_key
        return h

    def _timeout(self):
        return self.config.get("request_timeout", 120)

    def _ssl_context(self):
        return make_ssl_context(self.config.get("disable_ssl_verification", False))

    def make_api_request(self, prompt, system_prompt="", max_tokens=70, api_type=None):
        """Build a streaming completion/chat request."""
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            max_tokens = 70

        endpoint = self._endpoint()
        api_path = self._api_path()
        if api_type is None:
            api_type = self.config.get("api_type", "completions")
        api_type = "chat" if api_type == "chat" else "completions"
        model = self.config.get("model", "")
        temperature = self.config.get("temperature", 0.5)
        seed_val = self.config.get("seed", "")

        log_to_file("=== API Request Debug ===")
        log_to_file("Endpoint: %s" % endpoint)
        log_to_file("API Type: %s" % api_type)
        log_to_file("Model: %s" % model)
        log_to_file("Max Tokens: %s" % max_tokens)

        if api_type == "chat":
            url = endpoint + api_path + "/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            data = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": 0.9,
                "stream": True,
            }
        else:
            url = endpoint + api_path + "/completions"
            full_prompt = prompt
            if system_prompt:
                full_prompt = (
                    "SYSTEM PROMPT\n%s\nEND SYSTEM PROMPT\n%s"
                    % (system_prompt, prompt)
                )
            data = {
                "prompt": full_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": 0.9,
                "stream": True,
            }
            if not _is_openai_compatible(self.config) or seed_val:
                try:
                    data["seed"] = int(seed_val) if seed_val else 10
                except (TypeError, ValueError):
                    data["seed"] = 10

        if model:
            data["model"] = model

        json_data = json.dumps(data).encode("utf-8")
        log_to_file("Request data: %s" % json.dumps(data, indent=2))
        request = urllib.request.Request(
            url, data=json_data, headers=self._headers()
        )
        request.get_method = lambda: "POST"
        return request

    def extract_content_from_response(self, chunk, api_type="completions"):
        """Extract text content and optional thinking from API response chunk."""
        choices = chunk.get("choices", [])
        choice = choices[0] if choices else {}
        delta = choice.get("delta", {})

        finish_reason = choice.get("finish_reason") if choice else None
        if not finish_reason:
            finish_reason = chunk.get("finish_reason")
        if not finish_reason and choices:
            for c in choices:
                if isinstance(c, dict) and c.get("finish_reason"):
                    finish_reason = c.get("finish_reason")
                    break

        if api_type == "chat":
            content = (delta.get("content") or "") if delta else ""
        else:
            content = (choice.get("text") or "") if choice else ""

        thinking = _extract_thinking_from_delta(delta) if delta else ""
        if not thinking:
            thinking = _extract_thinking_from_delta(chunk)

        return content, finish_reason, thinking, delta

    def make_chat_request(self, messages, max_tokens=512, tools=None, stream=False):
        """Build a chat completions request from a full messages array."""
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            max_tokens = 512

        endpoint = self._endpoint()
        api_path = self._api_path()
        url = endpoint + api_path + "/chat/completions"
        model_name = self.config.get("model", "")
        temperature = self.config.get("temperature", 0.5)

        data = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
            "stream": stream,
        }
        if model_name:
            data["model"] = model_name
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"
            data["parallel_tool_calls"] = False

        json_data = json.dumps(data).encode("utf-8")
        log_to_file(
            "=== Chat Request (tools=%s, stream=%s) ===" % (bool(tools), stream)
        )
        log_to_file("URL: %s" % url)
        request = urllib.request.Request(
            url, data=json_data, headers=self._headers()
        )
        request.get_method = lambda: "POST"
        return request

    def stream_completion(
        self,
        prompt,
        system_prompt,
        max_tokens,
        api_type,
        append_callback,
        append_thinking_callback=None,
        stop_checker=None,
        dispatch_events=True,
    ):
        """Stream a completion/chat response via callbacks."""
        request = self.make_api_request(
            prompt, system_prompt, max_tokens, api_type=api_type
        )
        self.stream_request(
            request,
            api_type,
            append_callback,
            append_thinking_callback,
            stop_checker=stop_checker,
            dispatch_events=dispatch_events,
        )

    def stream_request(
        self,
        request,
        api_type,
        append_callback,
        append_thinking_callback=None,
        stop_checker=None,
        dispatch_events=True,
    ):
        """Stream a completion/chat response and append chunks via callbacks."""
        toolkit = self.ctx.getServiceManager().createInstanceWithContext(
            "com.sun.star.awt.Toolkit", self.ctx
        ) if dispatch_events else None
        ssl_context = self._ssl_context()
        timeout = self._timeout()

        log_to_file("=== Starting stream request ===")
        log_to_file("Request URL: %s" % request.full_url)
        try:
            with urllib.request.urlopen(
                request, context=ssl_context, timeout=timeout
            ) as response:
                for line in response:
                    if stop_checker and stop_checker():
                        log_to_file("stream_request: Stop requested by user.")
                        break

                    try:
                        if line.strip() and line.startswith(b"data: "):
                            payload = (
                                line[len(b"data: "):].decode("utf-8").strip()
                            )
                            if payload == "[DONE]":
                                log_to_file("stream_request: [DONE] received")
                                break
                            try:
                                chunk = json.loads(payload)
                            except json.JSONDecodeError:
                                continue
                            choices = chunk.get("choices", [])
                            if not choices:
                                log_to_file(
                                    "stream_request: empty choices, breaking"
                                )
                                break
                            content, finish_reason, thinking, _ = (
                                self.extract_content_from_response(
                                    chunk, api_type
                                )
                            )
                            if thinking and append_thinking_callback:
                                append_thinking_callback(thinking)
                            if content:
                                append_callback(content)
                            if dispatch_events and PROCESS_EVENTS_DURING_STREAM and toolkit and ((thinking and append_thinking_callback) or content):
                                try:
                                    toolkit.processEventsToIdle()
                                except Exception:
                                    pass

                            if finish_reason:
                                break
                    except Exception as e:
                        log_to_file("Error processing line: %s" % str(e))
                        raise
        except Exception as e:
            err_msg = format_error_message(e)
            log_to_file("ERROR in stream_request: %s -> %s" % (e, err_msg))
            raise Exception(err_msg)

    def stream_chat_response(
        self,
        messages,
        max_tokens,
        append_callback,
        append_thinking_callback=None,
        stop_checker=None,
        dispatch_events=True,
    ):
        """Stream a final chat response (no tools) using the messages array."""
        request = self.make_chat_request(
            messages, max_tokens, tools=None, stream=True
        )
        self.stream_request(
            request,
            "chat",
            append_callback,
            append_thinking_callback,
            stop_checker=stop_checker,
            dispatch_events=dispatch_events,
        )

    def request_with_tools(self, messages, max_tokens=512, tools=None):
        """Non-streaming chat request. Returns parsed response dict."""
        request = self.make_chat_request(
            messages, max_tokens, tools=tools, stream=False
        )
        ssl_context = self._ssl_context()
        timeout = self._timeout()

        try:
            with urllib.request.urlopen(
                request, context=ssl_context, timeout=timeout
            ) as response:
                body = response.read().decode("utf-8")
                result = json.loads(body)
        except Exception as e:
            err_msg = format_error_message(e)
            log_to_file("request_with_tools ERROR: %s -> %s" % (e, err_msg))
            raise Exception(err_msg)

        log_to_file("=== Tool response: %s" % json.dumps(result, indent=2))

        choice = result.get("choices", [{}])[0] if result.get("choices") else {}
        message = choice.get("message") or result.get("message") or {}
        finish_reason = choice.get("finish_reason") or result.get("done_reason")

        raw_content = message.get("content")
        content = _normalize_message_content(raw_content)

        return {
            "role": "assistant",
            "content": content,
            "tool_calls": message.get("tool_calls"),
            "finish_reason": finish_reason,
        }

    def stream_request_with_tools(
        self,
        messages,
        max_tokens=512,
        tools=None,
        append_callback=None,
        append_thinking_callback=None,
        stop_checker=None,
        dispatch_events=True,
    ):
        """Streaming chat request with tools. Returns same shape as request_with_tools."""
        log_to_file("stream_request_with_tools: building request (%d messages)..." % len(messages))
        request = self.make_chat_request(
            messages, max_tokens, tools=tools, stream=True
        )
        toolkit = self.ctx.getServiceManager().createInstanceWithContext(
            "com.sun.star.awt.Toolkit", self.ctx
        ) if dispatch_events else None
        ssl_context = self._ssl_context()
        timeout = self._timeout()

        message_snapshot = {}
        last_finish_reason = None
        last_chunk = None

        append_callback = append_callback or (lambda t: None)
        append_thinking_callback = append_thinking_callback or (lambda t: None)

        log_to_file("stream_request_with_tools: Opening URL: %s" % request.full_url)
        update_activity_state("stream_request_with_tools")
        debug_log(self.ctx, "stream_request_with_tools: about to open URL (blocking)")
        try:
            with urllib.request.urlopen(
                request, context=ssl_context, timeout=timeout
            ) as response:
                first_line_logged = False
                for line in response:
                    if stop_checker and stop_checker():
                        log_to_file(
                            "stream_request_with_tools: Stop requested by user."
                        )
                        last_finish_reason = "stop"
                        break

                    line_str = line.strip()
                    if not line_str or not line_str.startswith(b"data:"):
                        continue
                    idx = line_str.find(b":") + 1
                    payload = line_str[idx:].decode("utf-8").strip()
                    if payload == "[DONE]":
                        log_to_file(
                            "stream_request_with_tools: [DONE] received"
                        )
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        log_to_file(
                            "stream_request_with_tools: JSON decode error, payload=%s"
                            % payload[:200]
                        )
                        continue

                    last_chunk = chunk

                    if not first_line_logged:
                        first_line_logged = True
                        update_activity_state("stream_first_chunk")
                        debug_log(self.ctx, "stream_request_with_tools: first SSE line received")

                    choices = chunk.get("choices", [])
                    if not choices and (
                        message_snapshot.get("content")
                        or message_snapshot.get("tool_calls")
                    ):
                        log_to_file(
                            "stream_request_with_tools: empty choices, breaking"
                        )
                        last_finish_reason = last_finish_reason or "stop"
                        break

                    content, finish_reason, thinking, delta = (
                        self.extract_content_from_response(chunk, "chat")
                    )

                    if thinking:
                        append_thinking_callback(thinking)
                    if content:
                        append_callback(content)
                    if dispatch_events and PROCESS_EVENTS_DURING_STREAM and toolkit and (thinking or content):
                        try:
                            toolkit.processEventsToIdle()
                        except Exception:
                            pass

                    if delta:
                        accumulate_delta(message_snapshot, delta)

                    last_finish_reason = finish_reason
                    if last_finish_reason:
                        log_to_file(
                            "stream_request_with_tools: Breaking on finish_reason=%s"
                            % last_finish_reason
                        )
                        break

                log_to_file(
                    "stream_request_with_tools: Exited stream loop."
                )
                update_activity_state("stream_loop_exited")
                debug_log(self.ctx, "stream_request_with_tools: exited stream loop")
                if last_chunk:
                    choices = last_chunk.get("choices", [])
                    fr = None
                    if choices and isinstance(choices[0], dict):
                        fr = choices[0].get("finish_reason")
                    log_to_file(
                        "stream_request_with_tools: last chunk choices_len=%s finish_reason=%s keys=%s"
                        % (len(choices), fr, list(last_chunk.keys()))
                    )
                if not last_finish_reason:
                    if message_snapshot.get("tool_calls"):
                        last_finish_reason = "tool_calls"
                    else:
                        last_finish_reason = "stop"
                    log_to_file(
                        "stream_request_with_tools: Inferred finish_reason=%s"
                        % last_finish_reason
                    )
        except Exception as e:
            err_msg = format_error_message(e)
            log_to_file(
                "stream_request_with_tools ERROR: %s -> %s" % (e, err_msg)
            )
            raise Exception(err_msg)

        raw_content = message_snapshot.get("content")
        content = _normalize_message_content(raw_content)
        tool_calls = message_snapshot.get("tool_calls")

        return {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
            "finish_reason": last_finish_reason,
        }

    def chat_completion_sync(self, messages, max_tokens=512):
        """
        Synchronous chat completion (no streaming, no tools).
        Returns the assistant message content string.
        """
        result = self.request_with_tools(
            messages, max_tokens=max_tokens, tools=None
        )
        return result.get("content") or ""
