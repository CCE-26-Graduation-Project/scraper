"""Pluggable export back ends.

Hardened for production:
  * Decimal serialization. Money is emitted as a true JSON number via
    simplejson with use_decimal, so prices keep two place precision and never
    pass through a float. Standard json cannot do this.
  * Variant preservation. Nested variant objects serialize unchanged; the
    exporter never flattens or drops them.
  * Large catalog support. Records stream to JSONL with batched flushing
    (configurable), so memory stays flat and syscalls do not scale one to one
    with product count. The JSON array is optional, since for large catalogs
    the JSONL stream is the canonical feed.
  * Backward compatibility. Field names and order are untouched; the array
    file is still produced by default.

The pipeline writes through the Exporter interface, which is the seam that lets
PostgreSQL ingestion be added later with no spider or pipeline change.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import simplejson as sjson

logger = logging.getLogger(__name__)


def dumps(record: Dict[str, Any]) -> str:
    """Serialize a record to JSON with Decimal emitted as a true number."""
    return sjson.dumps(record, ensure_ascii=False, use_decimal=True)


class Exporter(ABC):
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def write(self, record: Dict[str, Any]) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class JsonLinesExporter(Exporter):
    """Stream records to a ``.jsonl`` file, optionally building a JSON array.

    Flushing is batched (every ``flush_every`` records) so a crash loses at
    most that many buffered lines while keeping write throughput high.
    """

    def __init__(
        self,
        jsonl_path: str,
        json_array_path: str = None,
        flush_every: int = 200,
        keep_previous_on_empty: bool = True,
    ) -> None:
        self.jsonl_path = jsonl_path
        self.json_array_path = json_array_path
        self.flush_every = max(1, int(flush_every))
        self.keep_previous_on_empty = keep_previous_on_empty
        self._tmp_path = jsonl_path + ".tmp"
        self._fh = None
        self._since_flush = 0
        self.count = 0

    def open(self) -> None:
        os.makedirs(os.path.dirname(self.jsonl_path) or ".", exist_ok=True)
        # Write to a temp file and swap on close, so a partial or blocked run
        # never leaves a half written or empty file in place of good data.
        self._fh = open(self._tmp_path, "w", encoding="utf-8")

    def write(self, record: Dict[str, Any]) -> None:
        if self._fh is None:
            raise RuntimeError("exporter used before open()")
        self._fh.write(dumps(record) + "\n")
        self.count += 1
        self._since_flush += 1
        if self._since_flush >= self.flush_every:
            self._fh.flush()
            self._since_flush = 0

    def close(self) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None

        # A run that produced nothing while a previous good file exists is
        # almost always a transient block, not a real emptying of the store.
        # Preserve the previous data rather than clobbering it with zero bytes.
        if (
            self.count == 0
            and self.keep_previous_on_empty
            and os.path.exists(self.jsonl_path)
            and os.path.getsize(self.jsonl_path) > 0
        ):
            logger.warning(
                "0 records scraped; keeping previous non empty %s (likely a transient block)",
                self.jsonl_path,
            )
            try:
                os.remove(self._tmp_path)
            except OSError:
                pass
            return

        self._atomic_rename()
        if self.json_array_path:
            self._build_json_array()

    def _atomic_rename(self) -> None:
        """Rename the temp file to the final path, with retry and fallback.

        On Windows, ``os.replace`` raises ``PermissionError`` when the
        destination is held open by another process (VS Code editor tab,
        Windows Defender scanning, Explorer preview panel). The strategy:

        1. Try ``os.replace`` (atomic on both POSIX and Windows) up to five
           times with a short sleep between attempts. The lock is usually
           transient and clears within a second.
        2. If all retries fail, try an explicit delete-then-rename. This is
           no longer atomic, but it works when the lock is released between
           the two steps and no prior replace succeeded.
        3. If that also fails, raise with an actionable message that includes
           the path of the safe ``.tmp`` file so the user can recover manually.
        """
        import time

        max_attempts = 5
        delay = 0.1  # seconds; doubles on each retry

        last_exc: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                os.replace(self._tmp_path, self.jsonl_path)
                return  # success
            except OSError as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    logger.debug(
                        "rename attempt %d/%d failed (%s); retrying in %.1fs",
                        attempt + 1, max_attempts, exc, delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 2.0)

        # All os.replace attempts failed.  Try delete-then-rename as a last
        # resort: it is not atomic but works when the lock is released between
        # the two syscalls.
        try:
            if os.path.exists(self.jsonl_path):
                os.remove(self.jsonl_path)
            os.rename(self._tmp_path, self.jsonl_path)
            logger.warning(
                "used non-atomic rename for %s after %d os.replace failures",
                self.jsonl_path, max_attempts,
            )
            return
        except OSError as fallback_exc:
            raise OSError(
                f"Could not rename {self._tmp_path!r} to {self.jsonl_path!r} after "
                f"{max_attempts} attempts. The complete data is safe in the .tmp file. "
                f"You can recover it manually with: "
                f"move \"{self._tmp_path}\" \"{self.jsonl_path}\". "
                f"Last error: {last_exc}. Fallback error: {fallback_exc}"
            ) from last_exc

    def _build_json_array(self) -> None:
        """Assemble a JSON array from the JSONL stream, one line at a time.

        Lines are already valid JSON (with Decimal numbers), so they are copied
        verbatim into the array, keeping peak memory bounded by a single line.
        """
        os.makedirs(os.path.dirname(self.json_array_path) or ".", exist_ok=True)
        with open(self.jsonl_path, "r", encoding="utf-8") as src, \
                open(self.json_array_path, "w", encoding="utf-8") as dst:
            dst.write("[\n")
            first = True
            for line in src:
                line = line.strip()
                if not line:
                    continue
                if not first:
                    dst.write(",\n")
                dst.write(line)
                first = False
            dst.write("\n]\n")


class PostgresExporter(Exporter):
    """Placeholder for direct PostgreSQL plus pgvector ingestion.

    Documents the integration point: implement write() to upsert on the
    deterministic product_id (so re crawls update rather than duplicate),
    persist variants to product_variants, and gate embedding regeneration on
    a content_hash change. Not wired in by default.
    """

    def __init__(self, dsn: str = None) -> None:
        self.dsn = dsn or os.getenv("DATABASE_URL")

    def open(self) -> None:
        raise NotImplementedError(
            "PostgresExporter is a documented placeholder. See README and db/schema.sql."
        )

    def write(self, record: Dict[str, Any]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
