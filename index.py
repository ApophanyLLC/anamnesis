"""SQLite-backed local search index for Anamnesis."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3

from .filesystem import ensure_private_directory, ensure_private_file
from .models import SearchResult, SessionDocument, SourceAuthorization, SourceIndexStatus


class AnamnesisSearchError(ValueError):
    """Raised when a user search query cannot be evaluated safely."""


class AnamnesisIndex:
    """Local session index with SQLite FTS5 search."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        ensure_private_directory(self.path.parent)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    last_indexed_at TEXT,
                    last_index_status TEXT,
                    drift_detected INTEGER NOT NULL DEFAULT 0,
                    parser_mode TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT,
                    modified_at TEXT,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY (source_id, session_id)
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    path TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(text, content='chunks', content_rowid='chunk_id');
                """
            )
            self._ensure_sources_columns(conn)
        ensure_private_file(self.path)

    def upsert_documents(self, documents: tuple[SessionDocument, ...]) -> int:
        self.initialize()
        indexed_chunks = 0
        with self._connect() as conn:
            for document in documents:
                self._insert_document(conn, document)
                indexed_chunks += sum(1 for exchange in document.exchanges if exchange.text.strip())
        return indexed_chunks

    def replace_source_documents(
        self,
        source: SourceAuthorization,
        documents: tuple[SessionDocument, ...],
        *,
        compact: bool = False,
        last_index_status: str = "success",
        drift_detected: bool = False,
        parser_mode: str = "structured",
        last_indexed_at: str | None = None,
    ) -> int:
        """Atomically replace one source's active index after parsing succeeds.

        FTS is rebuilt whenever prior chunks are removed so deleted source text
        is cleared from FTS shadow tables before the caller's later compaction.
        Set ``compact`` only for direct callers that are not already batching a
        single vacuum after multiple source replacements.
        """

        self.initialize()
        indexed_chunks = 0
        with self._connect() as conn:
            chunk_ids = self._chunk_ids_for_source(conn, source.source_id)
            for chunk_id in chunk_ids:
                conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
            conn.execute("DELETE FROM chunks WHERE source_id = ?", (source.source_id,))
            conn.execute("DELETE FROM sessions WHERE source_id = ?", (source.source_id,))
            if chunk_ids:
                conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
            self._upsert_source(
                conn,
                source,
                last_index_status=last_index_status,
                drift_detected=drift_detected,
                parser_mode=parser_mode,
                last_indexed_at=last_indexed_at,
            )
            for document in documents:
                self._insert_document(conn, document)
                indexed_chunks += sum(
                    1 for exchange in document.exchanges if exchange.text.strip()
                )
        if compact:
            self._vacuum()
        return indexed_chunks

    def upsert_source(self, source: SourceAuthorization) -> None:
        self.initialize()
        with self._connect() as conn:
            self._upsert_source(conn, source)

    def update_source_status(
        self,
        source: SourceAuthorization,
        *,
        last_index_status: str,
        drift_detected: bool,
        parser_mode: str,
        last_indexed_at: str | None = None,
    ) -> None:
        self.initialize()
        with self._connect() as conn:
            self._upsert_source(
                conn,
                source,
                last_index_status=last_index_status,
                drift_detected=drift_detected,
                parser_mode=parser_mode,
                last_indexed_at=last_indexed_at,
            )

    def source_statuses(self) -> tuple[SourceIndexStatus, ...]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    source_id,
                    source_type,
                    display_name,
                    path,
                    last_indexed_at,
                    last_index_status,
                    drift_detected,
                    parser_mode
                FROM sources
                ORDER BY source_id
                """
            ).fetchall()
        return tuple(
            SourceIndexStatus(
                source_id=str(row[0]),
                source_type=str(row[1]),
                display_name=str(row[2]),
                path=str(row[3]),
                last_indexed_at=row[4] if row[4] is not None else None,
                last_index_status=row[5] if row[5] is not None else None,
                drift_detected=bool(row[6]),
                parser_mode=row[7] if row[7] is not None else None,
            )
            for row in rows
        )

    def purge_source(self, source_id: str) -> int:
        self.initialize()
        with self._connect() as conn:
            chunk_ids = self._chunk_ids_for_source(conn, source_id)
            for chunk_id in chunk_ids:
                conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
            conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
            conn.execute("DELETE FROM sessions WHERE source_id = ?", (source_id,))
            conn.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
        self._vacuum()
        return len(chunk_ids)

    def vacuum(self) -> None:
        self.initialize()
        self._vacuum()

    def search(self, query: str, *, limit: int = 10) -> tuple[SearchResult, ...]:
        self.initialize()
        fts_query = _build_safe_fts_query(query)
        if not fts_query:
            return ()
        with self._connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT
                        chunks.source_id,
                        chunks.source_type,
                        chunks.session_id,
                        chunks.title,
                        chunks.path,
                        chunks.role,
                        snippet(chunks_fts, 0, '', '', ' ... ', 16) AS snippet_text,
                        bm25(chunks_fts) AS score
                    FROM chunks_fts
                    JOIN chunks ON chunks.chunk_id = chunks_fts.rowid
                    WHERE chunks_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
            except sqlite3.OperationalError as exc:
                raise AnamnesisSearchError("invalid search query") from exc
        return tuple(
            SearchResult(
                source_id=str(row[0]),
                source_type=str(row[1]),
                session_id=str(row[2]),
                title=str(row[3]),
                path=str(row[4]),
                role=str(row[5]),
                text=str(row[6]),
                score=float(row[7]),
            )
            for row in rows
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA secure_delete = ON")
        return conn

    def secure_delete_enabled(self) -> bool:
        if not self.path.exists():
            return True
        with self._connect() as conn:
            row = conn.execute("PRAGMA secure_delete").fetchone()
        return bool(row and row[0])

    def _vacuum(self) -> None:
        with self._connect() as conn:
            conn.execute("VACUUM")

    def _delete_session_chunks(
        self, conn: sqlite3.Connection, source_id: str, session_id: str
    ) -> None:
        chunk_ids = [
            row[0]
            for row in conn.execute(
                "SELECT chunk_id FROM chunks WHERE source_id = ? AND session_id = ?",
                (source_id, session_id),
            )
        ]
        for chunk_id in chunk_ids:
            conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
        conn.execute(
            "DELETE FROM chunks WHERE source_id = ? AND session_id = ?",
            (source_id, session_id),
        )

    def _chunk_ids_for_source(
        self, conn: sqlite3.Connection, source_id: str
    ) -> list[int]:
        return [
            row[0]
            for row in conn.execute(
                "SELECT chunk_id FROM chunks WHERE source_id = ?", (source_id,)
            )
        ]

    def _insert_document(
        self, conn: sqlite3.Connection, document: SessionDocument
    ) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO sessions (
                session_id, source_id, source_type, title, path, created_at,
                modified_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.session_id,
                document.source_id,
                document.source_type,
                document.title,
                str(document.path),
                document.created_at,
                document.modified_at,
                json.dumps(document.metadata, sort_keys=True),
            ),
        )
        self._delete_session_chunks(conn, document.source_id, document.session_id)
        for exchange in document.exchanges:
            if not exchange.text.strip():
                continue
            cursor = conn.execute(
                """
                INSERT INTO chunks (
                    source_id, source_type, session_id, title, path, role, text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.source_id,
                    document.source_type,
                    document.session_id,
                    document.title,
                    str(document.path),
                    exchange.role,
                    exchange.text,
                ),
            )
            conn.execute(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                (cursor.lastrowid, exchange.text),
            )

    def _upsert_source(
        self,
        conn: sqlite3.Connection,
        source: SourceAuthorization,
        *,
        last_index_status: str | None = None,
        drift_detected: bool = False,
        parser_mode: str | None = None,
        last_indexed_at: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO sources (
                source_id, source_type, display_name, path, last_indexed_at,
                last_index_status, drift_detected, parser_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.source_id,
                source.source_type,
                source.display_name,
                str(source.path),
                last_indexed_at,
                last_index_status,
                1 if drift_detected else 0,
                parser_mode,
            ),
        )

    def _ensure_sources_columns(self, conn: sqlite3.Connection) -> None:
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sources)").fetchall()
        }
        if "last_indexed_at" not in existing_columns:
            conn.execute("ALTER TABLE sources ADD COLUMN last_indexed_at TEXT")
        if "last_index_status" not in existing_columns:
            conn.execute("ALTER TABLE sources ADD COLUMN last_index_status TEXT")
        if "drift_detected" not in existing_columns:
            conn.execute(
                "ALTER TABLE sources ADD COLUMN drift_detected INTEGER NOT NULL DEFAULT 0"
            )
        if "parser_mode" not in existing_columns:
            conn.execute("ALTER TABLE sources ADD COLUMN parser_mode TEXT")


def _build_safe_fts_query(query: str) -> str:
    terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
    return " ".join(_quote_fts_term(term) for term in terms)


def _quote_fts_term(term: str) -> str:
    return f'"{term.replace(chr(34), chr(34) + chr(34))}"'
