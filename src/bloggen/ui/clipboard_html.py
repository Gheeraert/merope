"""Read the Windows "HTML Format" clipboard content, without extra dependencies.

Word, Google Docs (via the browser) and most rich text editors place an
HTML representation of the copied selection on the clipboard under the
custom-registered format "HTML Format", in addition to plain text. Tkinter
only ever gives access to plain text (``clipboard_get()``), so this module
talks to the Win32 clipboard API directly through :mod:`ctypes` (stdlib —
no ``pywin32`` dependency needed).

Two on-the-wire shapes are handled, both observed in practice:
- a full "CF_HTML" envelope: ``Version:0.9\\r\\nStartHTML:...`` header
  followed by an HTML document, with the actually-selected fragment
  delimited by ``StartFragment``/``EndFragment`` byte offsets;
- plain raw HTML with no envelope at all (seen from some sources).

Returns ``None`` (never raises) when unavailable: wrong platform, format
absent from the clipboard, or any Win32/decoding failure. Callers should
treat that as "fall back to normal plain-text paste".
"""

from __future__ import annotations

import re

_HTML_FORMAT_NAME = "HTML Format"
_HEADER_PROBE_SIZE = 400
_OFFSET_RE = re.compile(r"(StartHTML|EndHTML|StartFragment|EndFragment):(\d+)")


def read_html_clipboard() -> str | None:
    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, AttributeError):
        return None

    if not hasattr(ctypes, "windll"):
        return None

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterClipboardFormatW.restype = wintypes.UINT
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalSize.restype = ctypes.c_size_t

        html_format = user32.RegisterClipboardFormatW(_HTML_FORMAT_NAME)
        if not html_format:
            return None

        if not user32.OpenClipboard(None):
            return None
        try:
            handle = user32.GetClipboardData(html_format)
            if not handle:
                return None
            size = kernel32.GlobalSize(handle)
            if not size:
                return None
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return None
            try:
                raw = ctypes.string_at(pointer, size)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except OSError:
        return None

    return _extract_fragment(raw) or None


def _extract_fragment(raw: bytes) -> str:
    header_text = raw[:_HEADER_PROBE_SIZE].decode("ascii", errors="ignore")
    if header_text.lstrip().lower().startswith("version:"):
        offsets = {key: int(value) for key, value in _OFFSET_RE.findall(header_text)}
        if "StartFragment" in offsets and "EndFragment" in offsets:
            fragment = raw[offsets["StartFragment"] : offsets["EndFragment"]]
            return fragment.decode("utf-8", errors="replace")
        if "StartHTML" in offsets and "EndHTML" in offsets:
            fragment = raw[offsets["StartHTML"] : offsets["EndHTML"]]
            return fragment.decode("utf-8", errors="replace")
        return ""

    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
