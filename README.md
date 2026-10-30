# add_dois

Adds a DOI, a PDF link and an open-access copy (via Unpaywall) to each reference, and can download the PDFs, in a Google Scholar citation export (`.csv` or Apple Numbers `.numbers`).

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
python3 add_dois.py citations.csv --email you@example.org --download pdfs
```

| Option | Meaning |
|---|---|
| `input` | Google Scholar export (`.csv` or `.numbers`) |
| `-o`, `--output` | Output file (default: `<input>_with_doi.csv`, next to the input) |
| `--email` | Your email. It turns on the Unpaywall lookup, which requires an email, and is sent to Crossref for its faster, less throttled "polite" pool. Recommended; without it the two Unpaywall columns stay empty |
| `--download DIR` | Also download each paper's PDF into `DIR` (created if needed) |

It takes about 1 second per reference, a bit more with Unpaywall.

## Progress report

Each reference is reported as it finishes, followed by a summary:

```
177 references in citations.csv. Looking up DOIs on Crossref, open-access status on Unpaywall, downloading PDFs to pdfs/.
[1/177] Rajput 2025: 10.1523/eneuro.0382-24.2025 | OA: gold | PDF: open-access copy (4.2 MB)
[2/177] Akinrinade 2023: 10.1126/science.abq5158 | OA: closed | no PDF: www.science.org HTTP 403
[5/177] dos Reis Novais 2023: no confident DOI match
  rate-limited by api.crossref.org, waiting 2s
...
Done in 240s. Results in citations_with_doi.csv
  DOIs found:         163/177
  Open-access copies: 98/177 (gold 60, green 25, hybrid 8, bronze 5, closed 65)
  PDFs downloaded:    90/177 in pdfs/
  No DOI for:
    - Formation of the posterior commissure in the developing zebrafish embr
```

(The numbers above are only an illustration.) A failed download says why, for example "HTTP 403", "sent a web page, not a PDF" (a sign-in or cookie page), "could not connect" or "no direct PDF link known". "Rate-limited" lines are normal; the script waits and retries.

## Output

The input columns (Authors, Title, Publication, Volume, Number, Pages, Year, Publisher), plus:

- **DOI**: `https://doi.org/...` link
- **PDF link**: direct PDF link where the publisher's URL pattern is known, otherwise the article page
- **PDF link type**: `PDF` or `article page`
- **OA status**: Unpaywall's open-access category: `gold` (open-access journal), `hybrid` (open article in a subscription journal), `bronze` (free to read, no licence), `green` (repository or preprint copy), or `closed`
- **Open access PDF**: link to the best legal free copy (PDF if available, otherwise its landing page), even for paywalled papers that have a repository or preprint version
- **Downloaded file**: name of the saved PDF (only with `--download`), e.g. `Spikol_2024_Genetically_defined_nucleus_incertus_neurons.pdf`

Every field is quoted, so commas or semicolons in titles never shift columns.

## How it works

1. Each reference (title, first author, year) is searched with Crossref's `query.bibliographic`.
2. The top 8 candidates are scored on title similarity (anything below 0.9 is rejected), journal match, preprint vs published type, and year (±1).
3. The DOI is cleaned up (peer-review report DOIs become the article DOI, eLife version suffixes are removed). arXiv DOIs are built straight from the arXiv ID.
4. The PDF link is built from publisher patterns (Nature, Science, Wiley, Springer, Frontiers, eLife, PNAS, bioRxiv, arXiv, PLOS and others), or from Crossref's own full-text links. Cell Press and Elsevier papers get a ScienceDirect link.
5. With `--email`, each DOI is looked up on Unpaywall (`api.unpaywall.org/v2/<DOI>`), which reports the paper's open-access status and its best free copy.
6. With `--download`, the open-access copy is tried first, then the publisher PDF link. A file is kept only if it really is a PDF (publishers often answer with a sign-in or cookie page instead). PDFs already in the folder are not downloaded again, so an interrupted run can simply be restarted.

## Limitations

- Blank DOIs are expected for theses and for works Crossref doesn't index.
- A preprint whose title changed after your export may not match.
- When a paper exists both as a preprint and as an article, the wrong version is occasionally picked. Check the DOI against the Publication column.
- Links aren't checked for reachability. Paywalled publisher PDFs need your institution's access; check the Open access PDF column first.
- `--download` gets open-access papers reliably, and paywalled ones only when run on your institution's network or VPN. Even then, some publishers block scripted downloads. For the remaining papers, Zotero's "Add Item(s) by Identifier" (paste the DOIs) usually does better.
