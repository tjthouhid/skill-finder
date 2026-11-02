"""Shared helpers for Skill Finder (standard library only, no import side effects)."""
import re

_KEY_RE = re.compile(r"^([^\s:#][^:]*?)\s*:(?:\s+(.*))?$")
_BLOCK_RE = re.compile(r"^[>|][+-]?\d*$")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/", " ": " ", "0": "\0"}


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _is_skippable(line):
    s = line.strip()
    return not s or s.startswith("#")


def _scan_quoted(piece, quote):
    """Scan one line segment after an opening quote. Return (text, closed)."""
    out = []
    k = 0
    while k < len(piece):
        c = piece[k]
        if quote == "'":
            if c == "'":
                if piece[k + 1:k + 2] == "'":
                    out.append("'")
                    k += 2
                    continue
                return "".join(out), True
        else:
            if c == "\\" and k + 1 < len(piece):
                nxt = piece[k + 1]
                out.append(_ESCAPES.get(nxt, c + nxt))
                k += 2
                continue
            if c == '"':
                return "".join(out), True
        out.append(c)
        k += 1
    return "".join(out), False


def _parse_quoted(val, lines, i):
    """Parse a quoted scalar starting in `val`; continuation lines start at lines[i].

    Returns (value, next_i), or (None, i) when the closing quote is never found.
    """
    quote = val[0]
    pieces = []
    piece = val[1:]
    j = i
    while True:
        text, closed = _scan_quoted(piece, quote)
        if closed:
            pieces.append(text)
            break
        if j >= len(lines):
            return None, i
        pieces.append(text.rstrip())
        piece = lines[j].strip()
        j += 1
    return " ".join(p for p in pieces if p), j


def _scalar(raw):
    """Single-line scalar (list item): unquote when quoted, else keep raw."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        value, _ = _parse_quoted(raw, [], 0)
        if value is not None:
            return value
    return raw


def _parse_block_scalar(header, lines, i, indent):
    block = []
    while i < len(lines) and (not lines[i].strip() or _indent(lines[i]) > indent):
        block.append(lines[i])
        i += 1
    inner = [_indent(b) for b in block if b.strip()]
    base = min(inner) if inner else 0
    block = [b[base:].rstrip() if b.strip() else "" for b in block]
    while block and not block[-1]:
        block.pop()
    if header[0] == "|":
        return "\n".join(block), i
    paragraphs, cur = [], []
    for b in block:
        if b:
            cur.append(b)
        elif cur:
            paragraphs.append(" ".join(cur))
            cur = []
    if cur:
        paragraphs.append(" ".join(cur))
    return "\n".join(paragraphs), i


def _parse_list(lines, i, indent):
    items = []
    while i < len(lines):
        line = lines[i]
        if _is_skippable(line):
            i += 1
            continue
        s = line.strip()
        if _indent(line) >= indent and (s == "-" or s.startswith("- ")):
            items.append(_scalar(s[1:]))
        elif items and _indent(line) > indent:
            items[-1] = (items[-1] + " " + s).strip()
        else:
            break
        i += 1
    return items, i


def _parse_map(lines, i, indent, depth):
    result = {}
    n = len(lines)
    while i < n:
        line = lines[i]
        if _is_skippable(line):
            i += 1
            continue
        ind = _indent(line)
        if ind < indent:
            break
        m = _KEY_RE.match(line.strip())
        if ind > indent or not m:
            i += 1
            continue
        key, val = m.group(1), (m.group(2) or "").strip()
        i += 1
        if val == "":
            j = i
            while j < n and _is_skippable(lines[j]):
                j += 1
            if j < n:
                nxt = lines[j].strip()
                nind = _indent(lines[j])
                if nind >= indent and (nxt == "-" or nxt.startswith("- ")):
                    result[key], i = _parse_list(lines, j, indent)
                    continue
                if nind > indent:
                    if depth < 1:
                        result[key], i = _parse_map(lines, j, nind, depth + 1)
                    else:
                        raw = []
                        while i < n and (not lines[i].strip() or _indent(lines[i]) > indent):
                            raw.append(lines[i].strip())
                            i += 1
                        result[key] = "\n".join(raw).strip()
                    continue
            result[key] = ""
        elif val[0] in ("'", '"'):
            value, nxt_i = _parse_quoted(val, lines, i)
            if value is None:
                result[key] = val
            else:
                result[key], i = value, nxt_i
        elif _BLOCK_RE.match(val):
            result[key], i = _parse_block_scalar(val, lines, i, indent)
        else:
            result[key] = val
    return result, i


def parse_frontmatter(text):
    """Split a SKILL.md into (meta, body). meta is {} when there is no leading --- block."""
    lines = text.split("\n")
    if lines[0].rstrip("\r").lstrip("﻿") != "---":
        return {}, text
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r") == "---":
            end = idx
            break
    if end is None:
        raise ValueError("unclosed frontmatter")
    block = [ln.rstrip("\r").expandtabs(2) for ln in lines[1:end]]
    meta, _ = _parse_map(block, 0, 0, 0)
    return meta, "\n".join(lines[end + 1:])


def first_sentence(text):
    """Text up to the first ./!/? followed by whitespace or end, capped at 200 chars."""
    flat = " ".join(text.split())
    m = re.search(r"[.!?](?=\s|$)", flat)
    return (flat[:m.end()] if m else flat)[:200]
