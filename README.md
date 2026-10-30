# add_dois

Adds a DOI, a PDF link and an open-access copy (via Unpaywall) to each reference in a Google Scholar citation export (`.csv` or Apple Numbers `.numbers`).

## Requirements

- Python 3.9 or newer
- Internet access to `api.crossref.org`, and to `api.unpaywall.org` if you use `--email`
- `numbers-parser`, only for `.numbers` input:

  ```
  python3 -m pip install numbers-parser
  ```

## Usage

```
python3 add_dois.py "citations (1).numbers" --email you@example.org
python3 add_dois.py citations.csv -o references_with_doi.csv
```

| Option | Meaning |
|---|---|
| `input` | Google Scholar export (`.csv` or `.numbers`) |
| `-o`, `--output` | Output file (default: `<input>_with_doi.csv`, next to the input) |
| `--email` | Your email. It turns on the Unpaywall lookup, which requires an email, and is sent to Crossref for its faster, less throttled "polite" pool. Recommended; without it the two Unpaywall columns stay empty |

It takes about 1 second per reference, a bit more with Unpaywall.

## Output

The input columns (Authors, Title, Publication, Volume, Number, Pages, Year, Publisher), plus:

- **DOI**: `https://doi.org/...` link
- **PDF link**: direct PDF link where the publisher's URL pattern is known, otherwise the article page
- **PDF link type**: `PDF` or `article page`
- **OA status**: Unpaywall's open-access category: `gold` (open-access journal), `hybrid` (open article in a subscription journal), `bronze` (free to read, no licence), `green` (repository or preprint copy), or `closed`
- **Open access PDF**: link to the best legal free copy (PDF if available, otherwise its landing page), even for paywalled papers that have a repository or preprint version

Every field is quoted, so commas or semicolons in titles never shift columns.

## How it works

1. Each reference (title, first author, year) is searched with Crossref's `query.bibliographic`.
2. The top 8 candidates are scored on title similarity (anything below 0.9 is rejected), journal match, preprint vs published type, and year (±1).
3. The DOI is cleaned up (peer-review report DOIs become the article DOI, eLife version suffixes are removed). arXiv DOIs are built straight from the arXiv ID.
4. The PDF link is built from publisher patterns (Nature, Science, Wiley, Springer, Frontiers, eLife, PNAS, bioRxiv, arXiv, PLOS and others), or from Crossref's own full-text links. Cell Press and Elsevier papers get a ScienceDirect link.
5. With `--email`, each DOI is looked up on Unpaywall (`api.unpaywall.org/v2/<DOI>`), which reports the paper's open-access status and its best free copy.

## Limitations

- Blank DOIs are expected for theses and for works Crossref doesn't index.
- A preprint whose title changed after your export may not match.
- When a paper exists both as a preprint and as an article, the wrong version is occasionally picked. Check the DOI against the Publication column.
- Links aren't checked for reachability. Paywalled publisher PDFs need your institution's access; check the Open access PDF column first.
- To download the PDFs in bulk, paste the DOIs into Zotero's "Add Item(s) by Identifier".
