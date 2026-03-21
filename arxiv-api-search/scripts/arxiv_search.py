#!/usr/bin/env python3
"""
arXiv API Search with SQLite caching
Optimized for LLM consumption - filters noise, stores results
"""

import argparse
import json
import sqlite3
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
DB_PATH = SKILL_DIR / "data" / "arxiv_cache.db"
ARXIV_API = "https://export.arxiv.org/api/query"


def init_db():
    """Initialize SQLite database"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS papers (
            arxiv_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            abstract TEXT,
            published TEXT,
            updated TEXT,
            authors TEXT,
            categories TEXT,
            pdf_url TEXT,
            abs_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            query TEXT,
            arxiv_id TEXT,
            rank INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (arxiv_id) REFERENCES papers(arxiv_id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(published)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_session ON search_sessions(session_id)')

    conn.commit()
    return conn


def safe_request(url, max_retries=3):
    """Execute HTTP request with retry and exponential backoff"""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={'User-Agent': 'arxiv-skill/1.0'})
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 3.0 * (2 ** attempt)
            print(f"Request failed ({e}), retrying in {wait_time}s... ({attempt + 1}/{max_retries})", file=sys.stderr)
            time.sleep(wait_time)
    raise RuntimeError("Max retries exceeded")


def parse_arxiv_response(xml_data):
    """Parse arXiv API XML response, extract only essential fields"""
    ns = {
        'atom': 'http://www.w3.org/2005/Atom',
        'arxiv': 'http://arxiv.org/schemas/atom',
    }

    root = ET.fromstring(xml_data)
    papers = []

    for entry in root.findall('atom:entry', ns):
        id_elem = entry.find('atom:id', ns)
        arxiv_id = id_elem.text if id_elem is not None else ''
        arxiv_id = arxiv_id.split('/abs/')[-1] if '/abs/' in arxiv_id else arxiv_id

        title_elem = entry.find('atom:title', ns)
        title = title_elem.text.strip().replace('\n', ' ') if title_elem is not None and title_elem.text else ''

        abstract_elem = entry.find('atom:summary', ns)
        abstract = abstract_elem.text.strip().replace('\n', ' ') if abstract_elem is not None and abstract_elem.text else ''

        published_elem = entry.find('atom:published', ns)
        published = published_elem.text[:10] if published_elem is not None and published_elem.text else ''

        updated_elem = entry.find('atom:updated', ns)
        updated = updated_elem.text[:10] if updated_elem is not None and updated_elem.text else ''

        authors = []
        for author in entry.findall('atom:author', ns):
            name_elem = author.find('atom:name', ns)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text)

        categories = []
        for cat in entry.findall('atom:category', ns):
            if cat.get('term'):
                categories.append(cat.get('term'))

        papers.append({
            'arxiv_id': arxiv_id,
            'title': title,
            'abstract': abstract,
            'published': published,
            'updated': updated,
            'authors': authors,
            'categories': categories,
        })

    return papers


def search_arxiv(query, max_results=20, category=None):
    """Search arXiv API"""
    if category:
        query = f"cat:{category} AND ({query})"

    params = {
        'search_query': query,
        'start': 0,
        'max_results': max_results,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending'
    }

    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    xml_data = safe_request(url)
    return parse_arxiv_response(xml_data)


def save_papers(conn, papers, session_id=None, query=None):
    """Save papers to database"""
    cursor = conn.cursor()

    for rank, paper in enumerate(papers):
        cursor.execute('''
            INSERT OR REPLACE INTO papers
            (arxiv_id, title, abstract, published, updated, authors, categories, pdf_url, abs_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            paper['arxiv_id'],
            paper['title'],
            paper['abstract'],
            paper['published'],
            paper['updated'],
            json.dumps(paper['authors']),
            json.dumps(paper['categories']),
            f"https://arxiv.org/pdf/{paper['arxiv_id']}",
            f"https://arxiv.org/abs/{paper['arxiv_id']}",
        ))

        if session_id and query:
            cursor.execute('''
                INSERT INTO search_sessions (session_id, query, arxiv_id, rank)
                VALUES (?, ?, ?, ?)
            ''', (session_id, query, paper['arxiv_id'], rank))

    conn.commit()


def query_db(conn, keyword, session_id=None):
    """Query local database"""
    cursor = conn.cursor()

    if session_id:
        cursor.execute('''
            SELECT p.arxiv_id, p.title, p.abstract, p.published, p.categories
            FROM papers p
            JOIN search_sessions s ON p.arxiv_id = s.arxiv_id
            WHERE s.session_id = ?
            ORDER BY s.rank
        ''', (session_id,))
    else:
        cursor.execute('''
            SELECT arxiv_id, title, abstract, published, categories
            FROM papers
            WHERE title LIKE ? OR abstract LIKE ?
            ORDER BY published DESC
        ''', (f'%{keyword}%', f'%{keyword}%'))

    papers = []
    for row in cursor.fetchall():
        papers.append({
            'arxiv_id': row[0],
            'title': row[1],
            'abstract': row[2],
            'published': row[3],
            'categories': json.loads(row[4]) if row[4] else []
        })

    return papers


def format_output(papers, fmt='json', brief=False):
    """Format output for LLM consumption"""
    output_papers = []
    for p in papers:
        if brief:
            output_papers.append({
                'arxiv_id': p['arxiv_id'],
                'title': p['title'],
                'published': p['published'],
            })
        else:
            output_papers.append({
                'arxiv_id': p['arxiv_id'],
                'title': p['title'],
                'abstract': p['abstract'],
                'published': p['published'],
                'categories': p.get('categories', []),
            })

    if fmt == 'json':
        return json.dumps(output_papers, ensure_ascii=False, separators=(',', ':'))

    lines = []
    for i, p in enumerate(output_papers, 1):
        lines.append(f"## [{i}] {p['title']}")
        lines.append(f"- **arXiv**: {p['arxiv_id']}")
        lines.append(f"- **Published**: {p['published']}")
        if not brief:
            cats = p.get('categories', [])
            if cats:
                lines.append(f"- **Categories**: {', '.join(cats)}")
            abstract = p['abstract'][:500]
            if len(p['abstract']) > 500:
                abstract += '...'
            lines.append(f"- **Abstract**: {abstract}")
        lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='arXiv API Search with SQLite caching')
    parser.add_argument('--query', '-q', help='Search query')
    parser.add_argument('--max', '-m', type=int, default=20, help='Maximum results (default: 20)')
    parser.add_argument('--category', '-c', help='Category filter (e.g., cs.RO)')
    parser.add_argument('--db-query', '-d', help='Query local database instead of API')
    parser.add_argument('--session-id', '-s', help='Session ID for grouping results')
    parser.add_argument('--format', '-f', choices=['json', 'markdown'], default='json', help='Output format')
    parser.add_argument('--recent', type=int, help='Search papers from last N years (e.g., --recent 3)')
    parser.add_argument('--brief', action='store_true', help='Brief output: id, title, date only')

    args = parser.parse_args()

    conn = init_db()

    if args.db_query:
        papers = query_db(conn, args.db_query, args.session_id)
    elif args.query:
        query = args.query
        if args.recent:
            current_year = datetime.now().year
            start_year = current_year - args.recent
            # arXiv doesn't have native date filter, append year hint to query
            print(f"Note: --recent {args.recent} filters results after fetching (arXiv API has no date param)", file=sys.stderr)

        print(f"Searching arXiv: {query}...", file=sys.stderr)
        papers = search_arxiv(query, args.max, args.category)

        if args.recent:
            cutoff = f"{start_year}-01-01"
            before = len(papers)
            papers = [p for p in papers if p['published'] >= cutoff]
            if before != len(papers):
                print(f"Filtered by --recent {args.recent}: {before} -> {len(papers)} papers", file=sys.stderr)

        session_id = args.session_id or datetime.now().strftime('%Y%m%d_%H%M%S')
        save_papers(conn, papers, session_id, query)
        print(f"Saved {len(papers)} papers to database (session: {session_id})", file=sys.stderr)
    else:
        parser.print_help()
        conn.close()
        return

    print(format_output(papers, args.format, args.brief))
    conn.close()


if __name__ == '__main__':
    main()
