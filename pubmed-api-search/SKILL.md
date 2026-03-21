---
name: pubmed-api-search
description: Direct PubMed API search with Python filtering and SQLite storage. Use for searching biomedical literature, clinical studies, and life sciences papers.
---

# PubMed API Search

Search PubMed via NCBI E-utilities API (ESearch + EFetch). Results are cached in SQLite for offline re-query.

## Usage

**Python**: `python3` (fallback: ask user for path if not found)

```bash
# Basic search
python3 <skill_path>/scripts/pubmed_search.py --query "your search terms" --max 20

# With date range
python3 <skill_path>/scripts/pubmed_search.py --query "brain tumor" --mindate 2023/01/01 --max 30

# Recent papers only
python3 <skill_path>/scripts/pubmed_search.py --query "surgical robot" --recent 3

# Brief mode (id + title + date only, saves tokens for large batch screening)
python3 <skill_path>/scripts/pubmed_search.py --query "..." --brief

# Query local database (no API call)
python3 <skill_path>/scripts/pubmed_search.py --db-query "keyword"

# Markdown output
python3 <skill_path>/scripts/pubmed_search.py --query "..." --format markdown

# With API key (higher rate limit: 10 req/s vs 3 req/s)
python3 <skill_path>/scripts/pubmed_search.py --query "..." --api-key YOUR_KEY
```

## Parameters

| Param | Description |
|-------|-------------|
| `--query, -q` | Search query (supports PubMed syntax, see below) |
| `--max, -m` | Max results, default 20 |
| `--recent` | Filter to last N years |
| `--mindate` | Start date (YYYY/MM/DD or YYYY/MM or YYYY) |
| `--maxdate` | End date |
| `--brief` | Minimal output: pmid, title, pub_date only |
| `--format, -f` | `json` (default, compact) or `markdown` |
| `--db-query, -d` | Search local cache instead of API |
| `--api-key` | NCBI API key (optional, get from https://www.ncbi.nlm.nih.gov/account/) |

## Query Syntax

```
term1 AND term2                      # both required
term1 OR term2                       # either
term1 NOT term2                      # exclude
"exact phrase"[tiab]                 # title + abstract
keyword[MeSH]                        # MeSH term
author_name[Author]                  # author
journal_name[Journal]                # journal
review[pt]                           # publication type filter
```

Common field tags: `[ti]` title, `[ab]` abstract, `[tiab]` both, `[au]` author, `[ta]` journal, `[mh]` MeSH, `[pt]` pub type.

Publication types: `review[pt]`, `clinical trial[pt]`, `randomized controlled trial[pt]`, `case reports[pt]`, `meta-analysis[pt]`.

## Output Fields

Default: `pmid`, `title`, `abstract`, `pub_date`, `journal`
Brief mode: `pmid`, `title`, `pub_date`

Authors, DOI, keywords are stored in database but excluded from output to save tokens.

## Notes

- Results sorted by publication date (newest first)
- Rate limit: 3 req/s without API key, 10 req/s with key. Script has built-in retry with backoff.
- Database: `<skill_path>/data/pubmed_cache.db`
