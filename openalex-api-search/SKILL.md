---
name: openalex-api-search
description: Direct OpenAlex API search with Python filtering and SQLite storage. Use for searching scholarly literature across 240M+ works with citation data and open access filtering.
---

# OpenAlex API Search

Search OpenAlex via API. Results are cached in SQLite for offline re-query.

## Usage

**Python**: `python3 <skill_path>/scripts/openalex_search.py --query "your search terms" --max 20`

```
# Basic search
python3 <skill_path>/scripts/openalex_search.py --query "machine learning" --max 20

# With filter (OpenAlex filter syntax, comma = AND, pipe = OR)
python3 <skill_path>/scripts/openalex_search.py --query "neural networks" --filter "type:journal-article,is_oa:true" --max 20

# Recent papers only (last N years)
python3 <skill_path>/scripts/openalex_search.py --query "graph neural networks" --recent 3

# Brief mode (id + title + year only)
python3 <skill_path>/scripts/openalex_search.py --query "deep learning" --brief

# Query local database (no API call)
python3 <skill_path>/scripts/openalex_search.py --db-query "transformer" --max 50

# Markdown output
python3 <skill_path>/scripts/openalex_search.py --query "bioinformatics" --format markdown --max 20

# With sort
python3 <skill_path>/scripts/openalex_search.py --query "CRISPR" --sort "cited_by_count:desc" --max 20
```

## Shell Compatibility

**IMPORTANT**: The `--filter` value may contain commas and pipe characters that are interpreted differently across shells. You MUST follow these rules when generating commands:

- On **PowerShell (Windows)**: Always wrap `--filter` value in **single quotes** if it contains `|` (pipe). Single quotes in PowerShell prevent ALL special character interpretation.
  ```powershell
  python3 <skill_path>/scripts/openalex_search.py --query 'machine learning' --filter 'is_oa:true' --max 20
  python3 <skill_path>/scripts/openalex_search.py --query 'AI' --filter 'type:journal-article|book' --max 20
  ```
- On **Bash / Zsh (Linux/macOS)**: Use double quotes as shown in Usage examples above.
- **Prefer plain keyword queries** (no filter prefixes) whenever the search intent is straightforward — they work identically on all shells.
- **Never nest quotes inside the filter string**.

## Parameters

| Param | Description |
|-------|-------------|
| `--query, -q` | Search query (full-text search in title, abstract, keywords) |
| `--max, -m` | Max results, default 20 |
| `--recent` | Filter to last N years |
| `--brief` | Minimal output: openalex_id, title, publication_year only |
| `--format, -f` | `json` (default, compact) or `markdown` |
| `--db-query, -d` | Search local cache instead of API |
| `--session-id, -s` | Group results by session |
| `--filter, -F` | OpenAlex filter string (e.g., `is_oa:true,cited_by_count:>100`) |
| `--sort, -S` | Sort field (e.g., `cited_by_count:desc`, default: relevance) |

## Filter Syntax

Simple keyword searches work best and avoid shell escaping issues:
```
machine learning surgical navigation        # plain keywords (recommended, most compatible)
```

Common filter patterns (wrap in single quotes on PowerShell if containing `|`):
```
is_oa:true                                  # open access only
publication_year:2023                       # specific year
publication_year:>2020                      # after year
publication_year:2020-2024                  # year range
type:journal-article                        # document type
cited_by_count:>100                         # minimum citations
is_oa:true,publication_year:>2020           # multiple filters (comma = AND)
type:journal-article|book                   # multiple types (pipe = OR)
```

Common document types: `journal-article`, `book`, `dataset`, `proceedings-article`, `dissertation`.

## Output Fields

- Default: `openalex_id`, `title`, `abstract`, `publication_year`, `cited_by_count`
- Brief mode: `openalex_id`, `title`, `publication_year`

Authors, DOI, OA status are stored in database but excluded from output to save tokens.

## Notes

- Results sorted by relevance (default), or by specified `--sort` field
- OpenAlex rate limit: 1 req/s default, 10 req/s with polite pool (email). Script has built-in retry with backoff.
- Database: `<skill_path>/data/openalex_cache.db`
- OpenAlex covers 240M+ scholarly works across all disciplines
