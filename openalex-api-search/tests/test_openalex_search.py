import importlib.util
import io
import json
import sqlite3
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


def load_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "openalex_search.py"
    spec = importlib.util.spec_from_file_location("openalex_search", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_inmemory_conn():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE papers (
            openalex_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            abstract TEXT,
            publication_year TEXT,
            cited_by_count INTEGER,
            authors TEXT,
            doi TEXT,
            oa_status TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE search_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            session_id TEXT,
            openalex_id TEXT,
            rank INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


class TestOpenAlexSearch(unittest.TestCase):
    def test_reconstruct_abstract_basic(self):
        m = load_module()
        index = {"hello": [0], "world": [1], "again": [2]}
        self.assertEqual(m.reconstruct_abstract_from_inverted_index(index), "hello world again")

    def test_db_query_should_respect_max_limit(self):
        m = load_module()
        conn = build_inmemory_conn()
        cur = conn.cursor()
        for i in range(3):
            cur.execute(
                """
                INSERT INTO papers (openalex_id, title, abstract, publication_year, cited_by_count, authors, doi, oa_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"W{i}", f"alpha title {i}", "alpha abstract", "2024", i, "[]", "", ""),
            )
        conn.commit()

        out = io.StringIO()
        err = io.StringIO()
        with patch.object(m, "init_db", return_value=conn):
            with patch.object(sys, "argv", ["prog", "--db-query", "alpha", "--max", "1"]):
                with redirect_stdout(out), redirect_stderr(err):
                    m.main()

        items = json.loads(out.getvalue())
        self.assertEqual(len(items), 1, "db-query path should honor --max limit")

    def test_recent_filter_should_include_start_year(self):
        m = load_module()
        captured = {}

        class DummyConn:
            def close(self):
                return None

        def fake_search(query, max_results=20, filter_str=None, sort=None):
            captured["filter"] = filter_str
            return []

        with patch.object(m, "init_db", return_value=DummyConn()):
            with patch.object(m, "save_papers", return_value=None):
                with patch.object(m, "search_openalex", side_effect=fake_search):
                    with patch.object(sys, "argv", ["prog", "--query", "x", "--recent", "3"]):
                        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                            m.main()

        start_year = datetime.now().year - 3
        expected = f"publication_year:>{start_year - 1}"
        self.assertEqual(
            captured.get("filter"),
            expected,
            "recent filter should include the computed start year",
        )

    def test_negative_max_should_be_rejected(self):
        m = load_module()

        class DummyConn:
            def close(self):
                return None

        with patch.object(m, "init_db", return_value=DummyConn()):
            with patch.object(m, "save_papers", return_value=None):
                with patch.object(m, "search_openalex", return_value=[]):
                    with patch.object(sys, "argv", ["prog", "--query", "x", "--max", "-1"]):
                        with self.assertRaises(SystemExit):
                            m.main()

    def test_negative_recent_should_be_rejected(self):
        m = load_module()

        class DummyConn:
            def close(self):
                return None

        with patch.object(m, "init_db", return_value=DummyConn()):
            with patch.object(m, "save_papers", return_value=None):
                with patch.object(m, "search_openalex", return_value=[]):
                    with patch.object(sys, "argv", ["prog", "--query", "x", "--recent", "-1"]):
                        with self.assertRaises(SystemExit):
                            m.main()

    def test_same_session_should_not_duplicate_results(self):
        m = load_module()
        conn = build_inmemory_conn()
        papers = [
            {
                "openalex_id": "WTEST123",
                "title": "Test Paper",
                "abstract": "abc",
                "publication_year": "2025",
                "cited_by_count": 10,
                "authors": ["A"],
                "doi": "10.1/test",
                "oa_status": "gold",
            }
        ]
        m.save_papers(conn, papers, session_id="SAME_SESSION", query="q")
        m.save_papers(conn, papers, session_id="SAME_SESSION", query="q")

        rows = m.query_db(conn, keyword="ignored", session_id="SAME_SESSION")
        self.assertEqual(len(rows), 1, "session query should not return duplicate papers")

    def test_json_output_should_not_crash_on_gbk_stdout(self):
        m = load_module()
        payload = [
            {
                "openalex_id": "W1",
                "title": "CO\u2082 in medicine",
                "abstract": "contains unicode",
                "publication_year": "2024",
                "cited_by_count": 1,
            }
        ]
        rendered = m.format_output(payload, fmt="json", brief=False)
        fake_stdout = io.TextIOWrapper(io.BytesIO(), encoding="gbk", errors="strict")
        try:
            with patch.object(sys, "stdout", fake_stdout):
                print(rendered)
                fake_stdout.flush()
        except UnicodeEncodeError as exc:
            self.fail(f"json output should not raise UnicodeEncodeError on gbk stdout: {exc}")

    def test_safe_request_should_respect_system_proxy_by_default(self):
        m = load_module()
        proxy_args = []

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"results":[]}'

        class FakeOpener:
            def open(self, req, timeout=30):
                return FakeResp()

        def fake_proxy_handler(arg=None):
            proxy_args.append(arg)
            return object()

        def fake_build_opener(*handlers):
            return FakeOpener()

        with patch("urllib.request.ProxyHandler", side_effect=fake_proxy_handler):
            with patch("urllib.request.build_opener", side_effect=fake_build_opener):
                m.safe_request("https://api.openalex.org/works?search=test")

        self.assertIn(None, proxy_args, "safe_request should use system proxy settings by default")


if __name__ == "__main__":
    unittest.main(verbosity=2)

