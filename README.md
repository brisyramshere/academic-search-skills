# Academic Search Skills for Claude Code

Three Claude Code skills for searching academic papers via **arXiv**, **PubMed**, and **OpenAlex** APIs.

The scripts use Python stdlib only, produce token-efficient output, and cache results in local SQLite for offline re-query.

## Features

- Zero external dependencies for core scripts (`urllib`, `xml`, `sqlite3`)
- Token-optimized output (`json` compact mode + `--brief`)
- Local SQLite caching for offline search (`--db-query`)
- Retry with exponential backoff for transient network/API failures
- Mostly unified CLI interface across the three skills

## Skills

### arxiv-api-search

Search arXiv preprints (CS, Physics, Math, Engineering).

```bash
python3 arxiv-api-search/scripts/arxiv_search.py --query "transformer architecture" --max 20
python3 arxiv-api-search/scripts/arxiv_search.py --query "robot navigation" --category "cs.RO" --recent 2
python3 arxiv-api-search/scripts/arxiv_search.py --query "large language model" --brief
```

### pubmed-api-search

Search PubMed biomedical literature (medicine, clinical, life sciences).

```bash
python3 pubmed-api-search/scripts/pubmed_search.py --query "surgical navigation" --max 20
python3 pubmed-api-search/scripts/pubmed_search.py --query "brain tumor" --recent 3
python3 pubmed-api-search/scripts/pubmed_search.py --query "robotics[MeSH]" --brief
```

### openalex-api-search

Search OpenAlex cross-disciplinary literature with citation and open-access filters.

```bash
python3 openalex-api-search/scripts/openalex_search.py --query "machine learning" --max 20
python3 openalex-api-search/scripts/openalex_search.py --query "neural networks" --filter "is_oa:true" --max 20
python3 openalex-api-search/scripts/openalex_search.py --query "deep learning" --brief
python3 openalex-api-search/scripts/openalex_search.py --query "orthopedic robot" --filter "from_publication_date:2025-10-05,to_publication_date:2026-04-05"
```

## OpenAlex Notes

- Supports OpenAlex filter and sort:
  - `--filter "is_oa:true,publication_year:>2020"`
  - `--sort "cited_by_count:desc"`
- `--recent N` uses inclusive year semantics for "last N years".
- `--db-query` respects `--max`.
- Parameter validation:
  - `--max` must be `> 0`
  - `--recent` must be `> 0`
- Session deduplication is enabled for `(session_id, openalex_id)`.
- JSON output is ASCII-safe for Windows consoles (avoids `UnicodeEncodeError` on GBK terminals).
- Proxy behavior:
  - default: follow system proxy settings
  - set `OPENALEX_DISABLE_PROXY=1` to force no proxy
- Cache/database failures degrade gracefully for live API search; search results are still returned.

## Installation

Copy the skill directories into your Claude Code skills folder:

```bash
# Global (all projects)
cp -r arxiv-api-search ~/.claude/skills/
cp -r pubmed-api-search ~/.claude/skills/
cp -r openalex-api-search ~/.claude/skills/

# Project-local
mkdir -p .claude/skills
cp -r arxiv-api-search .claude/skills/
cp -r pubmed-api-search .claude/skills/
cp -r openalex-api-search .claude/skills/
```

> Python path defaults to `python3`. If needed, update command paths in each `SKILL.md`.

## Unified Parameters

| Param | Description | arXiv | PubMed | OpenAlex |
|-------|-------------|:-----:|:------:|:--------:|
| `--query, -q` | Search query | Y | Y | Y |
| `--max, -m` | Max results (default: 20) | Y | Y | Y |
| `--recent` | Papers from last N years | Y | Y | Y |
| `--brief` | Minimal output | Y | Y | Y |
| `--format, -f` | `json` or `markdown` | Y | Y | Y |
| `--db-query, -d` | Query local SQLite cache | Y | Y | Y |
| `--category, -c` | Category filter (e.g. `cs.RO`) | Y | - | - |
| `--mindate` | Start date (YYYY/MM/DD) | - | Y | - |
| `--maxdate` | End date | - | Y | - |
| `--api-key` | NCBI API key | - | Y | - |
| `--session-id, -s` | Group results by session | Y | - | Y |
| `--filter, -F` | Filter string | - | - | Y |
| `--sort, -S` | Sort field | - | - | Y |

## OpenAlex Tests

Run OpenAlex unit tests:

```bash
python -m unittest -v openalex-api-search/tests/test_openalex_search.py
```

## License

MIT
