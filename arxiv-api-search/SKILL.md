---
name: arxiv-api-search
description: Direct arXiv API search with Python filtering and SQLite storage. Use for real-time query of recent papers without local database.
---

# arXiv API Search

Search arXiv via API. Results are cached in SQLite for offline re-query.

## Usage

**Python**: `python3` (fallback: ask user for path if not found)

```
# Basic search
python3 <skill_path>/scripts/arxiv_search.py --query "your search terms" --max 20

# With category filter
python3 <skill_path>/scripts/arxiv_search.py --query "surgical navigation" --category "cs.RO" --max 20

# Recent papers only
python3 <skill_path>/scripts/arxiv_search.py --query "deep learning" --recent 3

# Brief mode (id + title + date only, saves tokens for large batch screening)
python3 <skill_path>/scripts/arxiv_search.py --query "..." --brief

# Query local database (no API call)
python3 <skill_path>/scripts/arxiv_search.py --db-query "keyword"

# Markdown output
python3 <skill_path>/scripts/arxiv_search.py --query "..." --format markdown
```

## Shell Compatibility

**IMPORTANT**: The `--query` value may contain parentheses and special characters that are interpreted differently across shells. You MUST follow these rules when generating commands:

- On **PowerShell (Windows)**: Always wrap `--query` value in **single quotes**. Single quotes in PowerShell prevent ALL special character interpretation.
  ```powershell
  python3 <skill_path>/scripts/arxiv_search.py --query 'deep learning surgical navigation' --max 20
  python3 <skill_path>/scripts/arxiv_search.py --query 'cat:(cs.RO) AND all:(navigation)' --max 20
  ```
- On **Bash / Zsh (Linux/macOS)**: Use double quotes as shown in Usage examples above.
- **Prefer plain keyword queries** (no field prefixes, no parentheses) whenever the search intent is straightforward — they work identically on all shells.
- **Never nest quotes** inside the query string. Do NOT generate `--query "ti:(\"some phrase\")"` — use `--query 'ti:(some phrase)'` on PowerShell or `--query "ti:(some phrase)"` on Bash instead.

## Parameters

| Param | Description |
|-------|-------------|
| `--query, -q` | Search query (supports arXiv syntax: `all:`, `ti:`, `abs:`, `au:`, `cat:`) |
| `--max, -m` | Max results, default 20 |
| `--category, -c` | Category filter (e.g. `cs.RO`, `cs.CV`, `cs.AI`, `cs.LG`, `eess.IV`) |
| `--recent` | Filter to last N years |
| `--brief` | Minimal output: arxiv_id, title, published only |
| `--format, -f` | `json` (default, compact) or `markdown` |
| `--db-query, -d` | Search local cache instead of API |
| `--session-id, -s` | Group results by session |

## Query Syntax

Simple keywords work best and avoid shell escaping issues:
```
deep learning surgical navigation     # plain keywords (recommended, most compatible)
```

Advanced syntax (wrap in single quotes on PowerShell):
```
all:(keyword1 OR keyword2)           # search title + abstract
ti:(exact title phrase)              # title only
cat:(cs.RO) AND all:(navigation)     # category + keyword
au:(Smith) AND ti:(robot)            # author + title
```

## Output Fields

Default: `arxiv_id`, `title`, `abstract`, `published`, `categories`
Brief mode: `arxiv_id`, `title`, `published`

Authors are stored in database but excluded from output to save tokens.

## Notes

- Results sorted by submission date (newest first)
- arXiv rate limit: ~1 request per 3 seconds. Script has built-in retry with backoff.
- Database: `<skill_path>/data/arxiv_cache.db`
