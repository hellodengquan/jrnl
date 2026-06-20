# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import logging
import time
from collections import OrderedDict

import keyring

from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import print_msg


class _MemoryPasswordCache:
    """Process-level LRU memory cache for passwords.

    Avoids repeatedly prompting for the same password during a single
    invocation (e.g. scanning multiple encrypted journals).

    LRU eviction, max entries configurable, TTL in seconds.
    """

    DEFAULT_MAX_ENTRIES = 16
    DEFAULT_TTL_SECONDS = 30 * 60

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._store: "OrderedDict[str, tuple[str, float]]" = OrderedDict()
        self._max = max_entries
        self._ttl = ttl_seconds

    def get(self, key: str) -> str | None:
        if key not in self._store:
            return None
        password, ts = self._store[key]
        if self._ttl > 0 and (time.time() - ts) > self._ttl:
            del self._store[key]
            logging.debug(f"Memory cache entry for {key} expired")
            return None
        self._store.move_to_end(key)
        return password

    def set(self, key: str, password: str) -> None:
        self._store[key] = (password, time.time())
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def clear(self, key: str | None = None) -> None:
        if key is None:
            self._store.clear()
        elif key in self._store:
            del self._store[key]


_MEMORY_CACHE = _MemoryPasswordCache()


def get_cached_password(journal_name: str) -> str | None:
    """First check the in-memory cache, then the system keyring."""
    pw = _MEMORY_CACHE.get(journal_name)
    if pw is not None:
        print_msg(
            Message(
                MsgText.PasswordRetrievedFromCache,
                MsgStyle.NORMAL,
                {"journal_name": journal_name},
            )
        )
        return pw

    keyring_pw = get_keyring_password(journal_name)
    if keyring_pw is not None:
        _MEMORY_CACHE.set(journal_name, keyring_pw)
        print_msg(
            Message(
                MsgText.PasswordRetrievedFromCache,
                MsgStyle.NORMAL,
                {"journal_name": journal_name},
            )
        )
        return keyring_pw

    return None


def set_cached_password(
    password: str,
    journal_name: str,
    persist_to_keyring: bool = False,
) -> None:
    """Store password in memory cache, optionally persist to keyring."""
    _MEMORY_CACHE.set(journal_name, password)
    print_msg(
        Message(
            MsgText.PasswordCachedInMemory,
            MsgStyle.NORMAL,
            {"journal_name": journal_name},
        )
    )
    if persist_to_keyring:
        set_keyring_password(password, journal_name)


def clear_cached_password(journal_name: str | None = None) -> None:
    _MEMORY_CACHE.clear(journal_name)


def get_keyring_password(journal_name: str = "default") -> str | None:
    try:
        return keyring.get_password("jrnl", journal_name)
    except keyring.errors.KeyringError as e:
        if not isinstance(e, keyring.errors.NoKeyringError):
            print_msg(Message(MsgText.KeyringRetrievalFailure, MsgStyle.ERROR))
        return None


def set_keyring_password(password: str, journal_name: str = "default") -> None:
    try:
        return keyring.set_password("jrnl", journal_name, password)
    except keyring.errors.KeyringError as e:
        if isinstance(e, keyring.errors.NoKeyringError):
            msg = Message(MsgText.KeyringBackendNotFound, MsgStyle.WARNING)
        else:
            msg = Message(MsgText.KeyringRetrievalFailure, MsgStyle.ERROR)
        print_msg(msg)
