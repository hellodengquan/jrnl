# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

"""Tag normalization for consistent matching across journal types.

Handles:
- NFC vs NFD Unicode forms (e.g. é = e + U+0301 vs U+00E9)
- Full-width / half-width katakana/alphanumerics (U+FF00..U+FFEF)
- Case folding (lowercase with Unicode rules)
- Consistent behavior across plain, DayOne, and Folder journals
"""

import logging
import unicodedata
from typing import Iterable

from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import print_msg


def _fold_width(char: str) -> str:
    """Map full-width characters (U+FF01..U+FF5E) to their ASCII equivalents,
    and half-width katakana variants to full-width where appropriate."""
    code = ord(char)
    if 0xFF01 <= code <= 0xFF5E:
        return chr(code - 0xFEE0)
    if code == 0x3000:
        return " "
    return char


def _fullwidth_to_ascii(text: str) -> str:
    return "".join(_fold_width(c) for c in text)


def normalize_tag(raw_tag: str, verbose: bool = False) -> str:
    """Return the canonical normalized form of a tag.

    Steps applied in order:
    1. Unicode NFC composition (prevents e + combining-acute vs é mismatch)
    2. Full-width ASCII -> half-width ASCII (for CJK mixed documents)
    3. Case-fold to lowercase using str.casefold() (handles ß -> ss etc.)

    The first character (tag symbol like @, +, #) is preserved as-is.
    """
    if not raw_tag:
        return raw_tag

    symbol = raw_tag[0]
    body = raw_tag[1:] if len(raw_tag) > 1 else ""

    if not body:
        return raw_tag

    normalized_body = unicodedata.normalize("NFC", body)
    if verbose and normalized_body != body:
        print_msg(
            Message(
                MsgText.TagNormalizedNFC,
                MsgStyle.NORMAL,
                {"raw": raw_tag, "normalized": symbol + normalized_body},
            )
        )

    normalized_body = _fullwidth_to_ascii(normalized_body)
    folded_body = normalized_body.casefold()

    if verbose and folded_body != normalized_body:
        print_msg(
            Message(
                MsgText.TagNormalizedCaseFold,
                MsgStyle.NORMAL,
                {"raw": raw_tag, "normalized": symbol + folded_body},
            )
        )

    return symbol + folded_body


def normalize_tags(tags: Iterable[str], verbose: bool = False) -> list[str]:
    """Normalize an iterable of tags, deduplicating while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        norm = normalize_tag(t, verbose=verbose)
        if norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def tags_match(tag_a: str, tag_b: str) -> bool:
    """Compare two tags after normalization (for equality checks)."""
    return normalize_tag(tag_a) == normalize_tag(tag_b)


def tag_in(tag: str, tag_collection: Iterable[str]) -> bool:
    """Check if a normalized tag appears in a collection (after normalization)."""
    norm = normalize_tag(tag)
    return any(normalize_tag(t) == norm for t in tag_collection)
