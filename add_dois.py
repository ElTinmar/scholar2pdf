"""Add DOI and PDF links to a Google Scholar citation export (.csv or .numbers).

Usage: python add_dois.py citations.numbers [-o out.csv] [--email you@example.org] [--download pdfs]
Needs `pip install numbers-parser` only for .numbers input.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

API = 'https://api.crossref.org/works'
PLOS = {'pbio': 'plosbiology', 'pgen': 'plosgenetics', 'pone': 'plosone', 'pcbi': 'ploscompbiol', 'pntd': 'plosntds'}
PATTERNS = {
    '10.1038': lambda d: f'https://www.nature.com/articles/{d.split("/", 1)[1]}.pdf',
    '10.1126': lambda d: f'https://www.science.org/doi/pdf/{d}',
    '10.3389': lambda d: f'https://www.frontiersin.org/articles/{d}/pdf',
    '10.7554': lambda d: f'https://elifesciences.org/articles/{d.split(".")[2]}.pdf',
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
COLOR = sys.stdout.isatty() and 'NO_COLOR' not in os.environ


def paint(text: str, code: str) -> str:
    return f'\033[{code}m{text}\033[0m' if COLOR else text


def green(text: str) -> str:
    return paint(text, '32')


def red(text: str) -> str:
    return paint(text, '31')


def yellow(text: str) -> str:
    return paint(text, '33')


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
            return json.load(urllib.request.urlopen(url, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            print(yellow(f'  rate-limited by {urllib.parse.urlparse(url).netloc}, waiting {wait}s'), flush=True)
            time.sleep(wait)
    raise RuntimeError(f'Kept being rate-limited: {url}')


def norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', s.lower())


def venue_match(item: dict, venue: str) -> bool:
    container, venue = norm((item.get('container-title') or [''])[0]), norm(venue)
    biorxiv = 'biorxiv' in venue and item['DOI'].startswith(('10.1101/', '10.64898/'))
    return biorxiv or bool(container and venue and (container in venue or venue in container))


def find(row: dict[str, str], email: str) -> dict:
    if m := re.search(r'arXiv:(\d{4}\.\d{4,5})', row['Publication'], re.I):
        return {'DOI': f'10.48550/arxiv.{m.group(1)}'}
    query = f"{row['Title']} {row['Authors'].split(',')[0]} {row['Year']}"
    params = {'query.bibliographic': query, 'rows': 8, 'select': 'DOI,title,issued,type,link,container-title'} | ({'mailto': email} if email else {})
    preprint = bool(re.search(r'biorxiv|arxiv', row['Publication'], re.I))
    best, best_score = {}, 0.0
    for item in get(f'{API}?{urllib.parse.urlencode(params)}')['message']['items']:
        sim = SequenceMatcher(None, norm(row['Title']), norm((item.get('title') or [''])[0])).ratio()
        year = (item.get('issued', {}).get('date-parts') or [[None]])[0][0]
        score = sim + 0.05 * ((item['type'] == 'posted-content') == preprint) + 0.1 * venue_match(item, row['Publication']) \
            + 0.03 * bool(year and row['Year'].isdigit() and abs(year - int(row['Year'])) <= 1)
        if sim >= 0.9 and score > best_score:
            best, best_score = item, score
    if best:
        best['DOI'] = re.sub(r'/v\d+/review\d+$', '', re.sub(r'(elife\.\d+)\.\d+$', r'\1', best['DOI'].lower()))
    return best


def unpaywall(doi: str, email: str) -> tuple[str, str]:
    try:
        record = get(f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return '', ''
        raise
    location = record.get('best_oa_location') or {}
    return record.get('oa_status') or '', location.get('url_for_pdf') or location.get('url') or ''


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


def download(urls: list[tuple[str, str]], path: Path) -> tuple[bool, str]:
    """Returns success and where the PDF came from, or why it failed."""
    if path.exists():
        return True, 'already downloaded'
    if not urls:
        return False, 'no direct PDF link known'
    reasons = []
    for source, url in urls:
        host = urllib.parse.urlparse(url).netloc
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/pdf,*/*'})
            data = urllib.request.urlopen(req, timeout=60).read()
        except urllib.error.HTTPError as e:
            reasons.append(f'{host} HTTP {e.code}')
            continue
        except Exception:
            reasons.append(f'could not connect to {host}')
            continue
        if not data.startswith(b'%PDF-'):
            reasons.append(f'{host} sent a web page, not a PDF')
            continue
        path.write_bytes(data)
        return True, f'{source} ({len(data) / 1e6:.1f} MB)'
    return False, '; '.join(reasons)


def file_name(row: dict[str, str]) -> str:
    stem = f"{row['Authors'].split(',')[0]}_{row['Year']}_{' '.join(row['Title'].split()[:8])}"
    return re.sub(r'[^\w-]+', '_', stem)[:100].strip('_') + '.pdf'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('input', type=Path)
    ap.add_argument('-o', '--output', type=Path)
    ap.add_argument('--email', default='', help='your email: enables Unpaywall and Crossref\'s faster "polite" pool')
    ap.add_argument('--download', type=Path, metavar='DIR', help='also download the PDFs into this folder')
    args = ap.parse_args()
    if args.download:
        args.download.mkdir(parents=True, exist_ok=True)

    def process(row: dict[str, str]) -> tuple[list[str], str]:
        item = find(row, args.email)
        if not item:
            return [''] * 6, red('no confident DOI match')
        link, kind = pdf_link(item)
        status, oa_pdf = unpaywall(item['DOI'], args.email) if args.email else ('', '')
        report = green(item['DOI']) + (f" | OA: {(red if status in ('closed', '') else green)(status or 'unknown')}" if args.email else '')
        name = ''
        if args.download:
            urls = [(src, u) for src, u in (('open-access copy', oa_pdf), ('publisher', link if kind == 'PDF' else '')) if u]
            ok, why = download(urls, args.download / file_name(row))
            name = file_name(row) if ok else ''
            report += ' | ' + (green(f'PDF: {why}') if ok else red(f'no PDF: {why}'))
        return [f"https://doi.org/{item['DOI']}", link, kind, status, oa_pdf, name], report

    rows = load(args.input)
    print(f'{len(rows)} references in {args.input.name}. Looking up DOIs on Crossref'
          + (', open-access status on Unpaywall' if args.email else ' (no --email: Unpaywall skipped)')
          + (f', downloading PDFs to {args.download}/' if args.download else '') + '.', flush=True)
    t0, extra = time.time(), []
    with ThreadPoolExecutor(2) as ex:
        for i, (row, (cells, report)) in enumerate(zip(rows, ex.map(process, rows)), 1):
            extra.append(cells)
            print(f"[{i}/{len(rows)}] {row['Authors'].split(',')[0]} {row['Year']}: {report}", flush=True)

    out = args.output or args.input.with_name(args.input.stem + '_with_doi.csv')
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow([*rows[0], 'DOI', 'PDF link', 'PDF link type', 'OA status', 'Open access PDF', 'Downloaded file'])
        w.writerows([*row.values(), *e] for row, e in zip(rows, extra))

    n = len(rows)
    print(f'\nDone in {time.time() - t0:.0f}s. Results in {out}')
    print(f'  DOIs found:         {green(str(sum(bool(e[0]) for e in extra)))}/{n}')
    if args.email:
        oa = Counter(e[3] for e in extra if e[3])
        print(f'  Open-access copies: {green(str(sum(bool(e[4]) for e in extra)))}/{n} (' + ', '.join(f'{k} {v}' for k, v in oa.most_common()) + ')')
    if args.download:
        print(f'  PDFs downloaded:    {green(str(sum(bool(e[5]) for e in extra)))}/{n} in {args.download}/')
    missing = [row['Title'][:70] for row, e in zip(rows, extra) if not e[0]]
    if missing:
        print(red('  No DOI for:') + '\n' + '\n'.join(red(f'    - {t}') for t in missing))


if __name__ == '__main__':
    main()
