"""Telegram message formatting utilities."""

import html
import re


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    Telegram MarkdownV2 requires escaping many special characters.
    """
    special_chars = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text


def _markdown_table_to_pre(text: str) -> str:
    """Convert markdown tables to <pre> blocks.

    Finds consecutive lines that look like table rows (start/end with |)
    and wraps them in <pre>, dropping the separator row (dashes).
    Must be called AFTER html.escape so content is safe.
    """

    def _format_table(match: re.Match) -> str:
        lines = match.group(0).strip().splitlines()
        rows: list[list[str]] = []
        for line in lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # Skip separator rows like |---|---|
            if all(re.fullmatch(r"-{2,}|:?-+:?", c) for c in cells):
                continue
            rows.append(cells)
        if not rows:
            return match.group(0)
        # Compute column widths
        col_count = max(len(r) for r in rows)
        widths = [0] * col_count
        for row in rows:
            for i, cell in enumerate(row):
                if i < col_count:
                    widths[i] = max(widths[i], len(cell))
        # Format aligned rows
        formatted: list[str] = []
        for row in rows:
            parts = []
            for i in range(col_count):
                cell = row[i] if i < len(row) else ""
                parts.append(cell.ljust(widths[i]))
            formatted.append("  ".join(parts))
        return "<pre>" + "\n".join(formatted) + "</pre>"

    # Match consecutive lines that start with |
    return re.sub(
        r"(?:^\|.+\|$\n?){2,}",
        _format_table,
        text,
        flags=re.MULTILINE,
    )


def markdown_to_telegram_html(text: str) -> str:
    """Convert common Markdown to Telegram-compatible HTML.

    Handles: code blocks, inline code, bold, italic, links, headers, tables.
    Telegram HTML supports: <b>, <i>, <code>, <pre>, <a href="">.
    """
    # HTML-escape first so we don't corrupt user text
    text = html.escape(text)

    # Tables → <pre> (before code blocks so they don't interfere)
    text = _markdown_table_to_pre(text)

    # Fenced code blocks: ```lang\n...\n``` → <pre>...</pre>
    text = re.sub(
        r"```(?:\w*)\n(.*?)```",
        lambda m: f"<pre>{m.group(1).rstrip()}</pre>",
        text,
        flags=re.DOTALL,
    )

    # Inline code: `...` → <code>...</code>
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # Italic: *text* or _text_ (but not inside words with underscores)
    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<i>\1</i>", text)

    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Headers: # Title → bold
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    return text


def strip_tool_markers(text: str) -> str:
    """Remove tool-use marker lines like '[tool: Read]' from message text.

    These appear in Claude Code session history and add noise to replays.
    """
    return re.sub(r"^\[tool:\s*\w+\]\s*$", "", text, flags=re.MULTILINE).strip()


def chunk_message(text: str, limit: int = 4096) -> list[str]:
    """Split a message into chunks at Telegram's character limit.

    Args:
        text: Text to chunk.
        limit: Maximum characters per chunk (default 4096 for Telegram).

    Returns:
        List of text chunks.
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    for i in range(0, len(text), limit):
        chunks.append(text[i:i + limit])
    return chunks
