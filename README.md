# Academic Search Skills for Claude Code

Two Claude Code skills for searching academic papers via **arXiv** and **PubMed** APIs. Zero external dependencies (Python stdlib only), token-optimized output, with SQLite caching for offline re-query.

## Features

- **Zero dependencies** — Pure Python stdlib (`urllib`, `xml`, `sqlite3`), no `pip install` needed
- **Token-optimized output** — Compact JSON, minimal fields, `--brief` mode for large batch screening
- **SQLite caching** — All results stored locally for offline querying across sessions
- **Retry with backoff** — Built-in exponential backoff for API rate limits and transient errors
- **Unified interface** — Both skills share consistent parameters (`--max`, `--recent`, `--brief`, `--format`)

## Skills

### arxiv-api-search

Search arXiv preprint server. Best for CS, Physics, Math, Engineering papers.

```bash
python3 arxiv-api-search/scripts/arxiv_search.py --query "transformer architecture" --max 20
python3 arxiv-api-search/scripts/arxiv_search.py --query "robot navigation" --category "cs.RO" --recent 2
python3 arxiv-api-search/scripts/arxiv_search.py --query "large language model" --brief  # id+title+date only
```

### pubmed-api-search

Search PubMed biomedical literature. Best for medical, clinical, and life sciences papers.

```bash
python3 pubmed-api-search/scripts/pubmed_search.py --query "surgical navigation" --max 20
python3 pubmed-api-search/scripts/pubmed_search.py --query "brain tumor" --recent 3
python3 pubmed-api-search/scripts/pubmed_search.py --query "robotics[MeSH]" --brief
```

## Installation

Copy the skill directories into your Claude Code skills folder:

```bash
# Global (all projects)
cp -r arxiv-api-search ~/.claude/skills/
cp -r pubmed-api-search ~/.claude/skills/

# Or project-local
mkdir -p .claude/skills
cp -r arxiv-api-search .claude/skills/
cp -r pubmed-api-search .claude/skills/
```

> **Python path**: Skills default to `python3`. If your Python is elsewhere, update the path in each `SKILL.md`.

## Unified Parameters

| Param | Description | arXiv | PubMed |
|-------|-------------|:-----:|:------:|
| `--query, -q` | Search query | Y | Y |
| `--max, -m` | Max results (default: 20) | Y | Y |
| `--recent` | Papers from last N years | Y | Y |
| `--brief` | Minimal output (id + title + date) | Y | Y |
| `--format, -f` | `json` (default) or `markdown` | Y | Y |
| `--db-query, -d` | Query local SQLite cache | Y | Y |
| `--category, -c` | Category filter (e.g. `cs.RO`) | Y | - |
| `--mindate` | Start date (YYYY/MM/DD) | - | Y |
| `--maxdate` | End date | - | Y |
| `--api-key` | NCBI API key (optional) | - | Y |
| `--session-id, -s` | Group results by session | Y | - |

## Token Optimization

Output is designed to minimize token consumption when fed back to LLMs:

- **Compact JSON**: No whitespace/indentation (`separators=(',',':')`)
- **Minimal fields**: Only `id`, `title`, `abstract`, `date`, `categories/journal` — authors excluded from output (stored in DB)
- **Brief mode**: `--brief` outputs only `id + title + date`, ~70% fewer tokens vs full output
- **No redundant URLs**: Paper links are omitted (reconstructable from IDs)

## License

MIT
