# add_dois

Adds a DOI and a PDF link to each reference in a Google Scholar citation export (`.csv` or Apple Numbers `.numbers`).

## Requirements

- Python 3.9 or newer
- Internet access to `api.crossref.org`
- `numbers-parser`, only for `.numbers` input:

  ```
  python3 -m pip install numbers-parser
  ```

## Usage

```
python3 add_dois.py "citations (1).numbers" --mailto you@example.org
python3 add_dois.py citations.csv -o references_with_doi.csv
```

| Option | Meaning |
|---|---|
| `input` | Google Scholar export (`.csv` or `.numbers`) |
| `-o`, `--output` | Output file (default: `<input>_with_doi.csv`, next to the input) |
| `--mailto` | Your email, sent to Crossref for its faster, less throttled "polite" pool (recommended) |

It takes about 1 second per reference.

## Output

The input columns (Authors, Title, Publication, Volume, Number, Pages, Year, Publisher), plus:

- **DOI**: `https://doi.org/...` link
- **PDF link**: direct PDF link where the publisher's URL pattern is known, otherwise the article page
- **PDF link type**: `PDF` or `article page`

Every field is quoted, so commas or semicolons in titles never shift columns.

## How it works

1. Each reference (title, first author, year) is searched with Crossref's `query.bibliographic`.
2. The top 8 candidates are scored on title similarity (anything below 0.9 is rejected), journal match, preprint vs published type, and year (±1).
3. The DOI is cleaned up (peer-review report DOIs become the article DOI, eLife version suffixes are removed). arXiv DOIs are built straight from the arXiv ID.
4. The PDF link is built from publisher patterns (Nature, Science, Wiley, Springer, Frontiers, eLife, PNAS, bioRxiv, arXiv, PLOS and others), or from Crossref's own full-text links. Cell Press and Elsevier papers get a ScienceDirect link.

## Limitations

- Blank DOIs are expected for theses and for works Crossref doesn't index.
- A preprint whose title changed after your export may not match.
- When a paper exists both as a preprint and as an article, the wrong version is occasionally picked. Check the DOI against the Publication column.
- Links aren't checked for reachability. Paywalled PDFs need your institution's access.
- To download the PDFs in bulk, paste the DOIs into Zotero's "Add Item(s) by Identifier".
