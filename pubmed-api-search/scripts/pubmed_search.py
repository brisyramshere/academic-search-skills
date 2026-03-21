#!/usr/bin/env python3
"""
PubMed API Search with SQLite caching
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

DB_PATH = Path(__file__).parent.parent / "data" / "pubmed_cache.db"
NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def init_db():
    """Initialize SQLite database with papers and search_sessions tables"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            pmid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            abstract TEXT,
            authors TEXT,
            journal TEXT,
            pub_date TEXT,
            doi TEXT,
            keywords TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            max_results INTEGER,
            mindate TEXT,
            maxdate TEXT,
            result_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_papers (
            session_id INTEGER,
            pmid TEXT,
            PRIMARY KEY (session_id, pmid),
            FOREIGN KEY (session_id) REFERENCES search_sessions(id),
            FOREIGN KEY (pmid) REFERENCES papers(pmid)
        )
    """)

    conn.commit()
    return conn


def safe_request(url, max_retries=3):
    """Execute HTTP request with retry and exponential backoff"""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={'User-Agent': 'pubmed-skill/1.0'})
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 1.0 * (2 ** attempt)
            print(f"Request failed ({e}), retrying in {wait_time}s... ({attempt + 1}/{max_retries})", file=sys.stderr)
            time.sleep(wait_time)
    raise RuntimeError("Max retries exceeded")


def search_pmids(query, max_results=20, mindate=None, maxdate=None, api_key=None):
    """Search PubMed and return PMIDs using ESearch API"""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "datetype": "pdat",
        "sort": "pub_date",
    }

    if mindate:
        params["mindate"] = mindate
    if maxdate:
        params["maxdate"] = maxdate
    if api_key:
        params["api_key"] = api_key

    url = f"{NCBI_BASE_URL}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    data = json.loads(safe_request(url))

    pmids = data.get("esearchresult", {}).get("idlist", [])
    return pmids


def fetch_papers(pmids, api_key=None):
    """Fetch paper details using EFetch API"""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml"
    }
    if api_key:
        params["api_key"] = api_key

    url = f"{NCBI_BASE_URL}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    xml_data = safe_request(url)

    papers = []
    root = ET.fromstring(xml_data)

    for article in root.findall(".//PubmedArticle"):
        pmid_elem = article.find(".//PMID")
        pmid = pmid_elem.text if pmid_elem is not None else ""

        title_elem = article.find(".//ArticleTitle")
        title = title_elem.text if title_elem is not None else "No title"
        if isinstance(title, str):
            title = title.strip()

        abstract_texts = article.findall(".//AbstractText")
        abstract_parts = []
        for abs_text in abstract_texts:
            label = abs_text.get("Label", "")
            text = "".join(abs_text.itertext())
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        authors_list = []
        for author in article.findall(".//Author"):
            last_name = author.find("LastName")
            fore_name = author.find("ForeName")
            if last_name is not None:
                name = last_name.text
                if fore_name is not None:
                    name = f"{name} {fore_name.text}"
                authors_list.append(name)
        authors = "; ".join(authors_list)

        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else ""

        pub_date = ""
        pub_date_elem = article.find(".//PubDate/Year")
        if pub_date_elem is not None:
            pub_date = pub_date_elem.text
        else:
            medline_date = article.find(".//PubDate/MedlineDate")
            if medline_date is not None and medline_date.text:
                pub_date = medline_date.text[:4] if len(medline_date.text) >= 4 else ""

        doi = ""
        for article_id in article.findall(".//ArticleId"):
            if article_id.get("IdType") == "doi":
                doi = article_id.text or ""
                break

        keywords_list = []
        for keyword in article.findall(".//Keyword"):
            if keyword.text:
                keywords_list.append(keyword.text)
        keywords = "; ".join(keywords_list)

        papers.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "journal": journal,
            "pub_date": pub_date,
            "doi": doi,
            "keywords": keywords,
        })

    return papers


def save_papers(conn, papers, query, max_results, mindate, maxdate):
    """Save papers to database and return session_id"""
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO search_sessions (query, max_results, mindate, maxdate, result_count)
        VALUES (?, ?, ?, ?, ?)
    """, (query, max_results, mindate, maxdate, len(papers)))
    session_id = cursor.lastrowid

    for paper in papers:
        cursor.execute("""
            INSERT OR REPLACE INTO papers (pmid, title, abstract, authors, journal, pub_date, doi, keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper["pmid"], paper["title"], paper["abstract"], paper["authors"],
            paper["journal"], paper["pub_date"], paper["doi"], paper["keywords"]
        ))

        cursor.execute("""
            INSERT OR IGNORE INTO session_papers (session_id, pmid)
            VALUES (?, ?)
        """, (session_id, paper["pmid"]))

    conn.commit()
    return session_id


def query_db(conn, keyword, limit=50):
    """Query database for papers matching keyword"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pmid, title, abstract, journal, pub_date, doi, keywords
        FROM papers
        WHERE title LIKE ? OR abstract LIKE ? OR keywords LIKE ?
        ORDER BY pub_date DESC
        LIMIT ?
    """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit))

    rows = cursor.fetchall()
    return [
        {
            "pmid": row[0],
            "title": row[1],
            "abstract": row[2],
            "journal": row[3],
            "pub_date": row[4],
            "doi": row[5],
            "keywords": row[6],
        }
        for row in rows
    ]


def format_output(papers, fmt="json", brief=False):
    """Format output for LLM consumption"""
    output_papers = []
    for p in papers:
        if brief:
            output_papers.append({
                "pmid": p["pmid"],
                "title": p["title"],
                "pub_date": p["pub_date"],
            })
        else:
            output_papers.append({
                "pmid": p["pmid"],
                "title": p["title"],
                "abstract": p["abstract"],
                "pub_date": p["pub_date"],
                "journal": p["journal"],
            })

    if fmt == "json":
        return json.dumps(output_papers, ensure_ascii=False, separators=(',', ':'))

    lines = []
    for i, p in enumerate(output_papers, 1):
        lines.append(f"## [{i}] {p['title']}")
        lines.append(f"- **PMID**: {p['pmid']}")
        lines.append(f"- **Published**: {p['pub_date']}")
        if not brief:
            lines.append(f"- **Journal**: {p['journal']}")
            abstract = p["abstract"][:500]
            if len(p["abstract"]) > 500:
                abstract += "..."
            lines.append(f"- **Abstract**: {abstract}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="PubMed API Search with SQLite caching")
    parser.add_argument("--query", "-q", type=str, help="Search query")
    parser.add_argument("--max", "-m", type=int, default=20, help="Maximum results (default: 20)")
    parser.add_argument("--mindate", type=str, help="Minimum date (YYYY/MM/DD or YYYY/MM or YYYY)")
    parser.add_argument("--maxdate", type=str, help="Maximum date (YYYY/MM/DD or YYYY/MM or YYYY)")
    parser.add_argument("--api-key", type=str, help="NCBI API key (optional, increases rate limit)")
    parser.add_argument("--db-query", "-d", type=str, help="Query local database instead of API")
    parser.add_argument("--format", "-f", type=str, choices=["json", "markdown"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--recent", type=int, help="Search papers from last N years (e.g., --recent 3)")
    parser.add_argument("--brief", action="store_true", help="Brief output: id, title, date only")

    args = parser.parse_args()

    conn = init_db()

    if args.db_query:
        papers = query_db(conn, args.db_query)
        print(format_output(papers, args.format, args.brief))
        conn.close()
        return

    if not args.query:
        parser.error("Either --query or --db-query is required")

    mindate = args.mindate
    if args.recent and not mindate:
        current_year = datetime.now().year
        mindate = f"{current_year - args.recent}/01/01"

    print(f"Searching PubMed: {args.query}", file=sys.stderr)
    pmids = search_pmids(args.query, args.max, mindate, args.maxdate, args.api_key)

    if not pmids:
        print("No results found.", file=sys.stderr)
        conn.close()
        return

    print(f"Found {len(pmids)} PMIDs, fetching details...", file=sys.stderr)
    time.sleep(0.34)

    papers = fetch_papers(pmids, args.api_key)

    save_papers(conn, papers, args.query, args.max, mindate, args.maxdate)

    print(format_output(papers, args.format, args.brief))

    conn.close()


if __name__ == "__main__":
    main()
