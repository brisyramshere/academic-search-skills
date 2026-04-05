#!/usr/bin/env python3
"""
OpenAlex API Search with SQLite caching
Optimized for LLM consumption - filters noise, stores results
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
DB_PATH = SKILL_DIR / "data" / "openalex_cache.db"
OPENALEX_API = "https://api.openalex.org/works"


def init_db():
    """Initialize SQLite database"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS papers (
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
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            session_id TEXT,
            openalex_id TEXT,
            rank INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(publication_year)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_session ON search_sessions(session_id)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_session_paper_unique ON search_sessions(session_id, openalex_id)')

    conn.commit()
    return conn


def safe_request(url, max_retries=3):
    """Execute HTTP request with retry and exponential backoff."""
    req = urllib.request.Request(url, headers={'User-Agent': 'openalex-skill/1.0'})
    disable_proxy = os.getenv('OPENALEX_DISABLE_PROXY', '').lower() in {'1', 'true', 'yes'}
    for attempt in range(max_retries):
        try:
            if disable_proxy:
                proxy_handler = urllib.request.ProxyHandler({})
            else:
                proxy_handler = urllib.request.ProxyHandler()
            opener = urllib.request.build_opener(proxy_handler)
            with opener.open(req, timeout=30) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 3.0 * (2 ** attempt)
            print(f"Request failed ({e}), retrying in {wait_time}s... ({attempt + 1}/{max_retries})", file=sys.stderr)
            time.sleep(wait_time)
    raise RuntimeError("Max retries exceeded")


def reconstruct_abstract_from_inverted_index(index):
    """Reconstruct abstract text from OpenAlex inverted index format"""
    if not index or not isinstance(index, dict):
        return ""
    
    # Find the maximum position to determine array size
    max_pos = 0
    for positions in index.values():
        if positions:
            max_pos = max(max_pos, max(positions))
    
    # Create array and place words at their positions
    words = [''] * (max_pos + 1)
    for word, positions in index.items():
        for pos in positions:
            if 0 <= pos < len(words):
                words[pos] = word
    
    # Join non-empty words with spaces
    return ' '.join(w for w in words if w)


def parse_openalex_response(json_data):
    """Parse OpenAlex API JSON response, extract only essential fields"""
    results = json_data.get('results', [])
    papers = []

    for item in results:
        # Extract openalex_id from URL like "https://openalex.org/W2741809807"
        openalex_id = item.get('id', '')
        if openalex_id.startswith('https://openalex.org/'):
            openalex_id = openalex_id.split('/')[-1]

        title = item.get('title', '') or ''

        # Prefer explicit 'abstract'; if missing, reconstruct from inverted index
        plain_abstract = item.get('abstract')
        if plain_abstract:
            abstract = plain_abstract
        else:
            inverted = item.get('abstract_inverted_index')
            if isinstance(inverted, dict):
                abstract = reconstruct_abstract_from_inverted_index(inverted)
            else:
                abstract = ""

        publication_year = item.get('publication_year', '')
        if publication_year is not None:
            publication_year = str(publication_year)
        else:
            publication_year = ''

        cited_by_count = item.get('cited_by_count', 0) or 0

        # Extract author names
        authors = []
        for authorship in item.get('authorships', []) or []:
            author = authorship.get('author', {})
            if author and author.get('display_name'):
                authors.append(author['display_name'])

        doi = item.get('doi', '') or ''

        # Extract OA status
        oa_status = ''
        open_access = item.get('open_access', {})
        if open_access:
            oa_status = open_access.get('oa_status', '') or ''

        papers.append({
            'openalex_id': openalex_id,
            'title': title,
            'abstract': abstract,
            'publication_year': publication_year,
            'cited_by_count': cited_by_count,
            'authors': authors,
            'doi': doi,
            'oa_status': oa_status,
        })

    return papers


def search_openalex(query, max_results=20, filter_str=None, sort=None):
    """Search OpenAlex API"""
    params = {
        'search': query,
        'per-page': max_results,
    }

    if filter_str:
        params['filter'] = filter_str
    if sort:
        params['sort'] = sort

    url = f"{OPENALEX_API}?{urllib.parse.urlencode(params)}"
    json_data = json.loads(safe_request(url))
    return parse_openalex_response(json_data)


def save_papers(conn, papers, session_id=None, query=None):
    """Save papers to database"""
    cursor = conn.cursor()

    for rank, paper in enumerate(papers):
        cursor.execute('''
            INSERT OR REPLACE INTO papers
            (openalex_id, title, abstract, publication_year, cited_by_count, authors, doi, oa_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            paper['openalex_id'],
            paper['title'],
            paper['abstract'],
            paper['publication_year'],
            paper['cited_by_count'],
            json.dumps(paper['authors']),
            paper['doi'],
            paper['oa_status'],
        ))

        if session_id and query:
            cursor.execute(
                'SELECT 1 FROM search_sessions WHERE session_id = ? AND openalex_id = ? LIMIT 1',
                (session_id, paper['openalex_id'])
            )
            if cursor.fetchone() is None:
                cursor.execute('''
                    INSERT OR IGNORE INTO search_sessions (session_id, query, openalex_id, rank)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, query, paper['openalex_id'], rank))

    conn.commit()


def query_db(conn, keyword, session_id=None, limit=50):
    """Query local database"""
    cursor = conn.cursor()

    if session_id:
        cursor.execute('''
            SELECT p.openalex_id, p.title, p.abstract, p.publication_year, p.cited_by_count
            FROM papers p
            JOIN search_sessions s ON p.openalex_id = s.openalex_id
            WHERE s.session_id = ?
            ORDER BY s.rank
            LIMIT ?
        ''', (session_id, limit))
    else:
        cursor.execute('''
            SELECT openalex_id, title, abstract, publication_year, cited_by_count
            FROM papers
            WHERE title LIKE ? OR abstract LIKE ?
            ORDER BY publication_year DESC
            LIMIT ?
        ''', (f'%{keyword}%', f'%{keyword}%', limit))

    papers = []
    for row in cursor.fetchall():
        papers.append({
            'openalex_id': row[0],
            'title': row[1],
            'abstract': row[2],
            'publication_year': row[3],
            'cited_by_count': row[4],
        })

    return papers


def format_output(papers, fmt='json', brief=False):
    """Format output for LLM consumption"""
    output_papers = []
    for p in papers:
        if brief:
            output_papers.append({
                'openalex_id': p['openalex_id'],
                'title': p['title'],
                'publication_year': p['publication_year'],
            })
        else:
            output_papers.append({
                'openalex_id': p['openalex_id'],
                'title': p['title'],
                'abstract': p['abstract'],
                'publication_year': p['publication_year'],
                'cited_by_count': p.get('cited_by_count', 0),
            })

    if fmt == 'json':
        # Keep JSON ASCII-only so it is safe on non-UTF8 terminals (e.g., Windows GBK).
        return json.dumps(output_papers, ensure_ascii=True, separators=(',', ':'))

    lines = []
    for i, p in enumerate(output_papers, 1):
        lines.append(f"## [{i}] {p['title']}")
        lines.append(f"- **OpenAlex**: {p['openalex_id']}")
        lines.append(f"- **Year**: {p['publication_year']}")
        if not brief:
            cited = p.get('cited_by_count', 0)
            if cited:
                lines.append(f"- **Cited by**: {cited}")
            abstract = p['abstract'][:500]
            if len(p['abstract']) > 500:
                abstract += '...'
            lines.append(f"- **Abstract**: {abstract}")
        lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='OpenAlex API Search with SQLite caching')
    parser.add_argument('--query', '-q', help='Search query')
    parser.add_argument('--max', '-m', type=int, default=20, help='Maximum results (default: 20)')
    parser.add_argument('--db-query', '-d', help='Query local database instead of API')
    parser.add_argument('--session-id', '-s', help='Session ID for grouping results')
    parser.add_argument('--format', '-f', choices=['json', 'markdown'], default='json', help='Output format')
    parser.add_argument('--recent', type=int, help='Search papers from last N years (e.g., --recent 3)')
    parser.add_argument('--brief', action='store_true', help='Brief output: id, title, year only')
    parser.add_argument('--filter', '-F', help='OpenAlex filter string (e.g., "is_oa:true,cited_by_count:>100")')
    parser.add_argument('--sort', '-S', help='OpenAlex sort field (e.g., "cited_by_count:desc")')

    args = parser.parse_args()

    if args.max <= 0:
        parser.error('--max must be a positive integer')
    if args.recent is not None and args.recent <= 0:
        parser.error('--recent must be a positive integer')

    conn = None
    try:
        conn = init_db()
    except sqlite3.Error as e:
        # Cache/database errors should not block live API searching.
        print(f"Warning: failed to initialize cache DB ({e}); continuing without cache.", file=sys.stderr)

    if args.db_query:
        if conn is None:
            print("Error: local cache DB unavailable, cannot use --db-query.", file=sys.stderr)
            return
        papers = query_db(conn, args.db_query, args.session_id, args.max)
    elif args.query:
        query = args.query

        # Build filter string
        filter_parts = []
        if args.recent:
            current_year = datetime.now().year
            start_year = current_year - args.recent
            # Include start year in "last N years" semantics.
            filter_parts.append(f"publication_year:>{start_year - 1}")
        if args.filter:
            filter_parts.append(args.filter)
        filter_str = ",".join(filter_parts) if filter_parts else None

        print(f"Searching OpenAlex: {query}...", file=sys.stderr)
        papers = search_openalex(query, args.max, filter_str, args.sort)

        if conn is not None:
            session_id = args.session_id or datetime.now().strftime('%Y%m%d_%H%M%S')
            try:
                save_papers(conn, papers, session_id, query)
                print(f"Saved {len(papers)} papers to database (session: {session_id})", file=sys.stderr)
            except sqlite3.Error as e:
                print(f"Warning: failed to save cache ({e}); results are still returned.", file=sys.stderr)
    else:
        parser.print_help()
        if conn is not None:
            conn.close()
        return

    print(format_output(papers, args.format, args.brief))
    if conn is not None:
        conn.close()


if __name__ == '__main__':
    main()
