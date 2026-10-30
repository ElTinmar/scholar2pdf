"""Add DOI and PDF links to a Google Scholar citation export (.csv or .numbers).

Usage: python add_dois.py citations.numbers [-o out.csv] [--mailto you@example.org]
Needs `pip install numbers-parser` only for .numbers input.
"""
import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

API = 'https://api.crossref.org/works'
PLOS = {'pbio': 'plosbiology', 'pgen': 'plosgenetics', 'pone': 'plosone', 'pcbi': 'ploscompbiol', 'pntd': 'plosntds'}
PATTERNS = {
    '10.1038': lambda d: f'https://www.nature.com/articles/{d.split("/", 1)[1]}.pdf',
    '10.1126': lambda d: f'https://www.science.org/doi/pdf/{d}',
    '10.3389': lambda d: f'https://www.frontiersin.org/articles/{d}/pdf',
    '10.7554': lambda d: f'https://elifesciences.org/articles/{re.search(r"elife\.(\d+)", d).group(1)}.pdf',
    '10.1002': lambda d: f'https://onlinelibrary.wiley.com/doi/pdf/{d}',
    '10.1111': lambda d: f'https://onlinelibrary.wiley.com/doi/pdf/{d}',
    '10.1113': lambda d: f'https://onlinelibrary.wiley.com/doi/pdf/{d}',
    '10.1007': lambda d: f'https://link.springer.com/content/pdf/{d}.pdf',
    '10.1186': lambda d: f'https://link.springer.com/content/pdf/{d}.pdf',
    '10.1073': lambda d: f'https://www.pnas.org/doi/pdf/{d}',
    '10.1101': lambda d: f'https://www.biorxiv.org/content/{d}.full.pdf',
    '10.64898': lambda d: f'https://www.biorxiv.org/content/{d}.full.pdf',
    '10.48550': lambda d: f'https://arxiv.org/pdf/{d.split("arxiv.", 1)[1]}',
    '10.1146': lambda d: f'https://www.annualreviews.org/doi/pdf/{d}',
    '10.1103': lambda d: f'https://journals.aps.org/prx/pdf/{d}',
    '10.1371': lambda d: f'https://journals.plos.org/{PLOS[d.split("journal.")[1][:4]]}/article/file?id={d}&type=printable',
}
TDM_HOSTS = ('syndication.highwire.org', 'api.wiley.com', 'harvest.aps.org', 'link.aps.org', 'api.elsevier.com', 'dx.plos.org')


def load(path: Path) -> list[dict[str, str]]:
    if path.suffix == '.numbers':
        from numbers_parser import Document
        header, *rows = Document(str(path)).sheets[0].tables[0].rows(values_only=True)
        fmt = lambda v: '' if v is None else str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
        return [dict(zip(header, map(fmt, r))) for r in rows if any(r)]
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def get(url: str) -> dict:
    for wait in (2, 5, 10, 20, 40, 60):
        try:
            return json.load(urllib.request.urlopen(url, timeout=60))['message']
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(wait)
    raise RuntimeError(f'Crossref kept rate-limiting: {url}')


def norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', s.lower())


def venue_match(item: dict, venue: str) -> bool:
    container, venue = norm((item.get('container-title') or [''])[0]), norm(venue)
    biorxiv = 'biorxiv' in venue and item['DOI'].startswith(('10.1101/', '10.64898/'))
    return biorxiv or bool(container and venue and (container in venue or venue in container))


def find(row: dict[str, str], mailto: str) -> dict:
    if m := re.search(r'arXiv:(\d{4}\.\d{4,5})', row['Publication'], re.I):
        return {'DOI': f'10.48550/arxiv.{m.group(1)}'}
    query = f"{row['Title']} {row['Authors'].split(',')[0]} {row['Year']}"
    params = {'query.bibliographic': query, 'rows': 8, 'select': 'DOI,title,issued,type,link,container-title'} | ({'mailto': mailto} if mailto else {})
    preprint = bool(re.search(r'biorxiv|arxiv', row['Publication'], re.I))
    best, best_score = {}, 0.0
    for item in get(f'{API}?{urllib.parse.urlencode(params)}')['items']:
        sim = SequenceMatcher(None, norm(row['Title']), norm((item.get('title') or [''])[0])).ratio()
        year = (item.get('issued', {}).get('date-parts') or [[None]])[0][0]
        score = sim + 0.05 * ((item['type'] == 'posted-content') == preprint) + 0.1 * venue_match(item, row['Publication']) \
            + 0.03 * bool(year and row['Year'].isdigit() and abs(year - int(row['Year'])) <= 1)
        if sim >= 0.9 and score > best_score:
            best, best_score = item, score
    if best:
        best['DOI'] = re.sub(r'/v\d+/review\d+$', '', re.sub(r'(elife\.\d+)\.\d+$', r'\1', best['DOI'].lower()))
    return best


def pdf_link(item: dict) -> tuple[str, str]:
    doi = item['DOI']
    if (prefix := doi.split('/')[0]) in PATTERNS:
        return PATTERNS[prefix](doi), 'PDF'
    for link in item.get('link', []):
        if link.get('content-type') == 'application/pdf' and not any(h in link['URL'] for h in TDM_HOSTS):
            return link['URL'].replace('http://', 'https://'), 'PDF'
        if m := re.search(r'api\.elsevier\.com/content/article/PII:(\w+)', link['URL']):
            return f'https://www.sciencedirect.com/science/article/pii/{m.group(1)}/pdfft', 'PDF'
    return f'https://doi.org/{doi}', 'article page'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('input', type=Path)
    ap.add_argument('-o', '--output', type=Path)
    ap.add_argument('--mailto', default='', help='your email, for Crossref\'s faster "polite" pool')
    args = ap.parse_args()

    rows = load(args.input)
    with ThreadPoolExecutor(2) as ex:
        items = list(ex.map(lambda r: find(r, args.mailto), rows))

    out = args.output or args.input.with_name(args.input.stem + '_with_doi.csv')
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow([*rows[0], 'DOI', 'PDF link', 'PDF link type'])
        for row, item in zip(rows, items):
            w.writerow([*row.values(), *([f"https://doi.org/{item['DOI']}", *pdf_link(item)] if item else ['', '', ''])])
    print(f'{sum(map(bool, items))}/{len(rows)} DOIs found -> {out}')


if __name__ == '__main__':
    main()
