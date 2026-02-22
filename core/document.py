"""Document helpers for LocalWriter."""


def get_full_document_text(model, max_chars=8000):
    """Get full document text for Writer, truncated to max_chars."""
    try:
        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        full = cursor.getString()
        if len(full) > max_chars:
            full = full[:max_chars] + "\n\n[... document truncated ...]"
        return full
    except Exception:
        return ""


def get_document_end(model, max_chars=4000):
    """Get the last max_chars of the document."""
    try:
        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoEnd(False)
        cursor.gotoStart(True)
        full = cursor.getString()
        if len(full) <= max_chars:
            return full
        return full[-max_chars:]
    except Exception:
        return ""


# goRight(nCount, bExpand) takes short; max 32767 per call
_GO_RIGHT_CHUNK = 8192


def get_document_length(model):
    """Return total character length of the document. Returns 0 on error."""
    try:
        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        return len(cursor.getString())
    except Exception:
        return 0


def get_text_cursor_at_range(model, start_offset, end_offset):
    """Return a text cursor that selects the character range [start_offset, end_offset).
    goRight is used in chunks because UNO's goRight takes short (max 32767).
    Returns None on error or invalid range."""
    try:
        doc_len = get_document_length(model)
        start_offset = max(0, min(start_offset, doc_len))
        end_offset = max(0, min(end_offset, doc_len))
        if start_offset > end_offset:
            start_offset, end_offset = end_offset, start_offset
        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        remaining = start_offset
        while remaining > 0:
            n = min(remaining, _GO_RIGHT_CHUNK)
            cursor.goRight(n, False)
            remaining -= n
        remaining = end_offset - start_offset
        while remaining > 0:
            n = min(remaining, _GO_RIGHT_CHUNK)
            cursor.goRight(n, True)
            remaining -= n
        return cursor
    except Exception:
        return None


def get_selection_range(model):
    """Return (start_offset, end_offset) character positions into the document.
    Cursor (no selection) = same start and end. Returns (0, 0) on error or no text range."""
    try:
        sel = model.getCurrentController().getSelection()
        if not sel or sel.getCount() == 0:
            vc = model.getCurrentController().getViewCursor()
            rng = vc
        else:
            rng = sel.getByIndex(0)
        if not rng or not hasattr(rng, "getStart") or not hasattr(rng, "getEnd"):
            return (0, 0)
        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoRange(rng.getStart(), True)
        start_offset = len(cursor.getString())
        cursor.gotoStart(False)
        cursor.gotoRange(rng.getEnd(), True)
        end_offset = len(cursor.getString())
        return (start_offset, end_offset)
    except Exception:
        return (0, 0)


def get_document_context_for_chat(model, max_context=8000, include_end=True, include_selection=True):
    """Build a single context string for chat with selection markers."""
    try:
        text = model.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        full = cursor.getString()
        doc_len = len(full)
    except Exception:
        return "Document length: 0.\n\n[DOCUMENT START]\n(empty)\n[END DOCUMENT]"

    start_offset, end_offset = (0, 0)
    if include_selection:
        start_offset, end_offset = get_selection_range(model)
        start_offset = max(0, min(start_offset, doc_len))
        end_offset = max(0, min(end_offset, doc_len))
        if start_offset > end_offset:
            start_offset, end_offset = end_offset, start_offset
        max_selection_span = 2000
        if end_offset - start_offset > max_selection_span:
            end_offset = start_offset + max_selection_span

    if include_end and doc_len > (max_context // 2):
        start_chars = max_context // 2
        end_chars = max_context - start_chars
        start_excerpt = full[:start_chars]
        end_excerpt = full[-end_chars:]
        start_excerpt = _inject_markers_into_excerpt(
            start_excerpt, 0, start_chars, start_offset, end_offset, "[DOCUMENT START]\n", "\n[DOCUMENT END]"
        )
        end_excerpt = _inject_markers_into_excerpt(
            end_excerpt, doc_len - end_chars, doc_len, start_offset, end_offset, "[DOCUMENT END]\n", "\n[END DOCUMENT]"
        )
        middle_note = "\n\n[... middle of document omitted ...]\n\n" if doc_len > max_context else ""
        return (
            "Document length: %d characters.\n\n%s%s%s"
            % (doc_len, start_excerpt, middle_note, end_excerpt)
        )
    else:
        take = min(doc_len, max_context)
        excerpt = full[:take]
        if doc_len > max_context:
            excerpt += "\n\n[... document truncated ...]"
        content_len = take
        excerpt = _inject_markers_into_excerpt(
            excerpt, 0, content_len, start_offset, end_offset, "[DOCUMENT START]\n", "\n[END DOCUMENT]"
        )
        return "Document length: %d characters.\n\n%s" % (doc_len, excerpt)


def _inject_markers_into_excerpt(excerpt_text, excerpt_start, excerpt_end, sel_start, sel_end, prefix, suffix):
    """Inject [SELECTION_START] and [SELECTION_END] at character positions relative to excerpt."""
    if sel_start >= excerpt_end or sel_end <= excerpt_start:
        return prefix + excerpt_text + suffix
    local_start = max(0, sel_start - excerpt_start)
    local_end = min(len(excerpt_text), sel_end - excerpt_start)
    before = excerpt_text[:local_start]
    between = excerpt_text[local_start:local_end]
    after = excerpt_text[local_end:]
    out = prefix + before + "[SELECTION_START]" + between + "[SELECTION_END]" + after + suffix
    return out
