"""Shared helpers for Skill Finder (standard library only, no import side effects)."""
import json
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
            parts = [val]
            while i < n and lines[i].strip() and not lines[i].lstrip().startswith("#") \
                    and _indent(lines[i]) > indent:
                parts.append(lines[i].strip())
                i += 1
            result[key] = " ".join(parts)
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


_SOURCE_ID_RE = re.compile(r"^[a-z0-9-]+$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _check_str(obj, key, path, errors, required=False):
    """Type-check obj[key] as str; record one error string when wrong or (if required) missing."""
    if key not in obj:
        if required:
            errors.append(f"{path}{key}: required")
        return
    if not isinstance(obj[key], str):
        errors.append(f"{path}{key}: must be a string")


def _check_str_list(obj, key, path, errors, required=False):
    if key not in obj:
        if required:
            errors.append(f"{path}{key}: required")
        return
    val = obj[key]
    if not isinstance(val, list):
        errors.append(f"{path}{key}: must be a list of strings")
        return
    for n, item in enumerate(val):
        if not isinstance(item, str):
            errors.append(f"{path}{key}[{n}]: must be a string")


def _check_slug(obj, key, path, errors):
    _check_str(obj, key, path, errors, required=True)
    if isinstance(obj.get(key), str) and not _SLUG_RE.match(obj[key]):
        errors.append(f"{path}{key}: must match ^[a-z0-9][a-z0-9-]*$")


def _check_object_list(data, key, errors):
    """Return enumerated items of data[key] when it is a list of objects, recording errors otherwise."""
    val = data.get(key)
    if not isinstance(val, list):
        errors.append(f"{key}: must be a list")
        return []
    items = []
    for n, item in enumerate(val):
        if isinstance(item, dict):
            items.append((n, item))
        else:
            errors.append(f"{key}[{n}]: must be an object")
    return items


def validate_source(data):
    """Return a list of error strings (JSON-path prefixed) for a source dict; empty means valid."""
    if not isinstance(data, dict):
        return ["<root>: must be an object"]
    errors = []
    _check_str(data, "source", "", errors, required=True)
    if isinstance(data.get("source"), str) and not _SOURCE_ID_RE.match(data["source"]):
        errors.append("source: must match ^[a-z0-9-]+$")
    _check_str(data, "label", "", errors, required=True)
    for key in ("homepage", "install", "install_all"):
        _check_str(data, key, "", errors)
    _check_str_list(data, "categories", "", errors)

    if "skills" not in data:
        errors.append("skills: required")
    else:
        for n, skill in _check_object_list(data, "skills", errors):
            path = f"skills[{n}]."
            _check_slug(skill, "slug", path, errors)
            _check_str(skill, "summary", path, errors, required=True)
            for key in ("name", "guide_slug", "category", "use_when"):
                _check_str(skill, key, path, errors)
            _check_str_list(skill, "aliases", path, errors)

    if "journeys" in data:
        for n, journey in _check_object_list(data, "journeys", errors):
            path = f"journeys[{n}]."
            _check_slug(journey, "slug", path, errors)
            _check_str(journey, "name", path, errors, required=True)
            _check_str_list(journey, "skills", path, errors, required=True)
            for key in ("tagline", "fits"):
                _check_str(journey, key, path, errors)
            if "phases" in journey and (isinstance(journey["phases"], bool)
                                        or not isinstance(journey["phases"], int)):
                errors.append(f"{path}phases: must be an integer")

    if "routes" in data:
        for n, route in _check_object_list(data, "routes", errors):
            path = f"routes[{n}]."
            _check_str(route, "name", path, errors, required=True)
            for key in ("shortcut", "note"):
                _check_str(route, key, path, errors)
            if "steps" not in route:
                errors.append(f"{path}steps: required")
            elif not isinstance(route["steps"], list):
                errors.append(f"{path}steps: must be a list of [slug, text] pairs")
            else:
                for m, step in enumerate(route["steps"]):
                    if not (isinstance(step, list) and len(step) == 2
                            and all(isinstance(x, str) for x in step)):
                        errors.append(f"{path}steps[{m}]: must be a [slug, text] pair of strings")
    return errors


def load_sources(sources_dir):
    """Load valid *.json sources in sorted filename order. Return (sources, warnings).

    Each unreadable/invalid file yields exactly one warning "<file>: <error(s)>".
    """
    sources, warnings = [], []
    for path in sorted(sources_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(f"{path.name}: {exc}")
            continue
        errors = validate_source(data)
        if errors:
            warnings.append(f"{path.name}: " + "; ".join(errors))
            continue
        sources.append(data)
    return sources, warnings


def expand_install(template, slug, agent):
    """Fill {slug}/{agent} in an install template; None stays None."""
    if template is None:
        return None
    return template.replace("{slug}", slug).replace("{agent}", agent)
