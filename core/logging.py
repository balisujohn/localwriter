"""Simple file logging for LocalWriter."""
import os
import json
import time
import threading

# Hang visibility: shared state for watchdog (main thread updates, watchdog reads)
_activity_state = {"phase": "", "round_num": -1, "tool_name": None, "last_activity": 0.0}
_activity_lock = threading.Lock()
_watchdog_started = False
_watchdog_interval_sec = 15
_watchdog_threshold_sec = 30

# Debug logging enable flag — set by main.py from config on startup
_debug_logging_enabled = False


def set_debug_logging(enabled):
    """Enable or disable debug file logging."""
    global _debug_logging_enabled
    _debug_logging_enabled = enabled


def agent_log(location, message, data=None, hypothesis_id=None, run_id=None):
    """Write one NDJSON line to agent debug log (~/.localwriter/agent.log)."""
    if not _debug_logging_enabled:
        return
    payload = {"location": location, "message": message, "timestamp": int(time.time() * 1000)}
    if data is not None:
        payload["data"] = data
    if hypothesis_id is not None:
        payload["hypothesisId"] = hypothesis_id
    if run_id is not None:
        payload["runId"] = run_id
    line = json.dumps(payload) + "\n"
    try:
        log_dir = os.path.join(os.path.expanduser("~"), ".localwriter")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "agent.log"), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def debug_log(ctx, msg):
    """Write one line to chat debug log with timestamp prepended."""
    if not _debug_logging_enabled:
        return
    try:
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        ms = int((time.time() % 1) * 1000)
        line = "%s.%03d | %s\n" % (now, ms, msg)
    except Exception:
        line = msg + "\n"
    try:
        log_dir = os.path.join(os.path.expanduser("~"), ".localwriter")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "chat_debug.log"), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def update_activity_state(phase, round_num=None, tool_name=None):
    """Update shared activity state (call from main thread at phase boundaries).
    Pass phase='' when returning control to LibreOffice so the watchdog stops checking."""
    with _activity_lock:
        _activity_state["phase"] = phase
        _activity_state["last_activity"] = time.monotonic()
        if round_num is not None:
            _activity_state["round_num"] = round_num
        if tool_name is not None:
            _activity_state["tool_name"] = tool_name


def _watchdog_loop(ctx, status_control):
    """Daemon thread: if no activity for threshold, log and set status to Hung: ..."""
    while True:
        time.sleep(_watchdog_interval_sec)
        with _activity_lock:
            phase = _activity_state["phase"]
            round_num = _activity_state["round_num"]
            tool_name = _activity_state["tool_name"]
            last = _activity_state["last_activity"]
        if not phase:
            continue
        elapsed = time.monotonic() - last
        if elapsed < _watchdog_threshold_sec:
            continue
        msg = "WATCHDOG: no activity for %ds; phase=%s round=%s tool=%s" % (
            int(elapsed), phase, round_num, tool_name if tool_name else "")
        debug_log(ctx, msg)
        if status_control:
            try:
                hung_text = "Hung: %s round %s" % (phase, round_num)
                if tool_name:
                    hung_text += " %s" % tool_name
                status_control.setText(hung_text)
            except Exception:
                pass


def start_watchdog_thread(ctx, status_control=None):
    """Start the hang-detection watchdog (idempotent). Pass status_control to set Hung: ... in UI."""
    global _watchdog_started
    with _activity_lock:
        if _watchdog_started:
            return
        _watchdog_started = True
    t = threading.Thread(target=_watchdog_loop, args=(ctx, status_control), daemon=True)
    t.start()


def log_to_file(message):
    """Write a log line to ~/.localwriter/log.txt. Respects debug logging flag."""
    if not _debug_logging_enabled:
        return
    try:
        import datetime
        log_dir = os.path.join(os.path.expanduser("~"), ".localwriter")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "log.txt")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("%s - %s\n" % (now, message))
    except Exception:
        pass
