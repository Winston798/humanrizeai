#!/usr/bin/env python3
"""HumanizeAI batching with mandatory contextual review and minimal repairs."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

UNITS = re.compile(r'[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]|[^\s\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]+')
PARAGRAPH = re.compile(r'\n[ \t]*\n(?:[ \t]*\n)*')
SENTENCE = re.compile(r'[.!?。！？][\"\u201d\u2019\)\]]*\s+$')


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def split_text(text, limit=180):
    """Return a prefix and chunks whose exact source reconstruction equals text."""
    if not 1 <= limit <= 200:
        raise ValueError('Batch limit must be between 1 and 200.')
    prefix = text[:len(text) - len(text.lstrip())]
    remaining = text[len(prefix):]
    chunks = []
    while remaining.strip():
        para = PARAGRAPH.search(remaining)
        end = para.start() if para else len(remaining)
        tokens = list(UNITS.finditer(remaining[:end]))
        if len(tokens) > limit:
            cut = tokens[limit].start()
            for i in range(limit, max(1, limit // 2), -1):
                boundary = tokens[i].start()
                if SENTENCE.search(remaining[:boundary]):
                    cut = boundary
                    break
            end = cut
        raw = remaining[:end]
        chunk = raw.rstrip()
        rest = remaining[len(chunk):]
        sep_len = len(rest) - len(rest.lstrip())
        sep = rest[:sep_len]
        if not chunk:
            raise ValueError('Unable to split source.')
        chunks.append({'index': len(chunks) + 1, 'input': chunk,
                       'after': sep, 'output': None, 'attempts': 0})
        remaining = rest[sep_len:]
    if remaining:
        if chunks:
            chunks[-1]['after'] += remaining
        else:
            prefix += remaining
    return prefix, chunks


def save(path, job):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def load(job_dir):
    path = Path(job_dir).resolve() / 'job.json'
    job = json.loads(path.read_text(encoding='utf-8'))
    source = job['prefix'] + ''.join(c['input'] + c['after'] for c in job['chunks'])
    if job.get('version') != 1 or digest(source) != job['source_sha256']:
        raise ValueError('Job source/version integrity check failed.')
    if any(c['index'] != i or not c['input'].strip() or
           len(UNITS.findall(c['input'])) > job['limit'] or
           (c['output'] is not None and not c['output'].strip())
           for i, c in enumerate(job['chunks'], 1)):
        raise ValueError('Invalid job chunk data.')
    job.setdefault('review', None)  # Existing jobs keep website results but need review.
    return path, job


REVIEW_CHECKS = ('full_source', 'full_website_output', 'logic_and_causality',
                 'facts_and_meaning', 'global_context_and_boundaries',
                 'omissions_and_references')
CATEGORIES = {'logic', 'fact', 'context', 'omission', 'reference', 'terminology'}


def complete_website(job):
    if any(c['output'] is None for c in job['chunks']):
        raise ValueError('Website processing is incomplete.')


def merged(job, field):
    return job['prefix'] + ''.join(c[field] + c['after'] for c in job['chunks'])


def write_text_exact(path, text):
    with path.open('w', encoding='utf-8', newline='') as stream:
        stream.write(text)


def read_text_exact(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return stream.read()


def prepare_review(path, job):
    complete_website(job)
    folder = path.parent / 'review'
    folder.mkdir(exist_ok=True)
    source, raw = merged(job, 'input'), merged(job, 'output')
    template = {'version': 1, 'source_sha256': digest(source),
                'website_sha256': digest(raw),
                'checks': {name: False for name in REVIEW_CHECKS},
                'summary': '', 'edits': [], 'unresolved': []}
    # The stable source/raw snapshots are regenerated; authored reports are retained.
    write_text_exact(folder / 'source.txt', source)
    write_text_exact(folder / 'website-raw.txt', raw)
    template_path = folder / 'report-template.json'
    save(template_path, template)
    print('Review required. Read full source and website output, then follow the skill review protocol.')
    print('Review folder: ' + str(folder))


def apply_report(job, report):
    complete_website(job)
    source, raw = merged(job, 'input'), merged(job, 'output')
    if report.get('version') != 1 or report.get('source_sha256') != digest(source) or report.get('website_sha256') != digest(raw):
        raise ValueError('Review belongs to a different source or website result.')
    checks = report.get('checks')
    if not isinstance(checks, dict) or any(checks.get(name) is not True for name in REVIEW_CHECKS):
        raise ValueError('Full contextual review checks have not all been confirmed.')
    if not isinstance(report.get('summary'), str) or not report['summary'].strip():
        raise ValueError('A substantive review summary is required, including for zero edits.')
    edits, unresolved = report.get('edits'), report.get('unresolved')
    if not isinstance(edits, list) or not isinstance(unresolved, list) or any(not isinstance(x, str) or not x.strip() for x in unresolved):
        raise ValueError('Edits and unresolved findings must be lists; unresolved findings must be nonempty text.')
    located = []
    for number, edit in enumerate(edits, 1):
        if not isinstance(edit, dict) or edit.get('category') not in CATEGORIES:
            raise ValueError(f'Edit {number}: invalid category.')
        for key in ('before', 'after', 'reason', 'evidence'):
            if not isinstance(edit.get(key), str):
                raise ValueError(f'Edit {number}: {key} must be text.')
        before, after = edit['before'], edit['after']
        if not before or before == after or not edit['reason'].strip() or not edit['evidence'].strip():
            raise ValueError(f'Edit {number}: supply a real change, reason and supporting evidence.')
        if 'start' in edit:
            start = edit['start']
            if type(start) is not int or start < 0 or raw[start:start + len(before)] != before:
                raise ValueError(f'Edit {number}: start does not match the exact raw text.')
        else:
            start = raw.find(before)
            if start < 0 or raw.find(before, start + 1) != -1:
                raise ValueError(f'Edit {number}: before must occur once; widen the anchor or specify start.')
        located.append((start, start + len(before), after, number))
    located.sort()
    for left, right in zip(located, located[1:]):
        if left[1] > right[0]:
            raise ValueError('Review edits overlap. Combine the repair into one minimal replacement.')
    final = raw
    for start, end, after, _ in reversed(located):
        final = final[:start] + after + final[end:]
    if not final.strip():
        raise ValueError('Reviewed text cannot be empty.')
    return final


def record_review(path, job, report_path):
    report = json.loads(Path(report_path).read_text(encoding='utf-8-sig'))
    final = apply_report(job, report)
    folder = path.parent / 'review'
    folder.mkdir(exist_ok=True)
    save(folder / 'report.json', report)
    write_text_exact(folder / 'corrected-draft.txt', final)
    job['review'] = {'status': 'applied', 'source_sha256': report['source_sha256'],
                     'website_sha256': report['website_sha256'],
                     'report_sha256': digest(json.dumps(report, ensure_ascii=False, sort_keys=True)),
                     'draft_sha256': digest(final), 'edit_count': len(report['edits']),
                     'unresolved': report['unresolved'], 'final_read_note': None}
    save(path, job)
    print(f'Repairs applied: {len(report["edits"])}. Unresolved: {len(report["unresolved"])}.')
    print('Read corrected-draft.txt in full with its context before review-complete.')
    print('Draft SHA-256: ' + digest(final))


def checked_review(path, job, require_verified=False):
    complete_website(job)
    review = job.get('review')
    if not isinstance(review, dict):
        raise ValueError('Mandatory contextual review is missing. Run review-prepare first.')
    folder = path.parent / 'review'
    report = json.loads((folder / 'report.json').read_text(encoding='utf-8-sig'))
    final = apply_report(job, report)
    if (review.get('source_sha256') != report['source_sha256'] or
            review.get('website_sha256') != report['website_sha256'] or
            review.get('report_sha256') != digest(json.dumps(report, ensure_ascii=False, sort_keys=True)) or
            review.get('draft_sha256') != digest(final) or
            read_text_exact(folder / 'corrected-draft.txt') != final or
            review.get('unresolved') != report['unresolved']):
        raise ValueError('Review or draft changed. Reapply the review and reread the final draft.')
    if require_verified and (review.get('status') != 'verified' or report['unresolved'] or not review.get('final_read_note')):
        raise ValueError('Final reread is not confirmed, or unresolved findings remain.')
    return final


def finish_review(path, job, confirmed_sha256, note):
    final = checked_review(path, job)
    if job['review']['unresolved']:
        raise ValueError('Unresolved review findings remain; do not declare the workflow complete.')
    if confirmed_sha256 != digest(final) or not note.strip():
        raise ValueError('Confirm the exact reread draft hash and supply a final contextual reread note.')
    job['review']['status'] = 'verified'
    job['review']['final_read_note'] = note.strip()
    save(path, job)
    print('Contextual review, minimal repairs and final reread recorded. Final export is now allowed.')


def cli(job, cwd, command, *args):
    exe = shutil.which('npx.cmd' if os.name == 'nt' else 'npx')
    if not exe:
        raise RuntimeError('Node/npm (npx) is required for browser automation.')
    # Browser snippets contain single quotes only; payloads are base64 to avoid
    # Windows .cmd argument quoting and source-text command injection.
    cmd = [exe, '--yes', '--package', '@playwright/cli', 'playwright-cli',
           '-s=' + job['session'], '--json', command, *args]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=60,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError('Browser CLI returned no JSON: ' + (result.stderr or result.stdout)[-1200:])
    if result.returncode or payload.get('isError'):
        raise RuntimeError(str(payload.get('error', payload))[:1600])
    return payload


def code(job, cwd, body):
    snippet = 'async (page) => { ' + body.replace('\n', ' ') + ' }'
    result = cli(job, cwd, 'run-code', snippet).get('result')
    return json.loads(result) if isinstance(result, str) else result


READ = """
const input = page.getByRole('textbox', {name:'Input Textarea', exact:true});
const output = page.getByRole('textbox', {name:'Humanized output', exact:true});
const button = page.getByRole('button', {name:'Humanize AI', exact:true});
"""

POLL = READ + """
let alerts = [];
for (const item of await page.locator('[role=alert], [role=dialog]').all()) {
  if (await item.isVisible()) alerts.push((await item.innerText()).slice(0, 1000));
}
let challenge = false;
for (const frame of await page.locator('iframe[title*=challenge], iframe[title*=Challenge]').all()) {
  if (await frame.isVisible()) challenge = true;
}
return {input:await input.inputValue(), output:await output.inputValue(),
        ready:await button.isEnabled(), alerts:alerts.join(' '), challenge};
"""


def accept(path, job, index, text):
    c = job['chunks'][index - 1] if 1 <= index <= len(job['chunks']) else None
    if c is None or c['index'] != index or not text.strip():
        raise ValueError('Invalid index or empty output.')
    if c['output'] is not None and c['output'] != text.strip():
        raise ValueError('A different output is already saved; refusing overwrite.')
    if any(x['output'] is None for x in job['chunks'][:index - 1]):
        raise ValueError('Record results in source order.')
    if job['pending'] is not None and job['pending']['index'] != index:
        raise ValueError('A different batch is pending; refusing to clear it.')
    if c['output'] is None:
        job['review'] = None
    c['output'] = text.strip()
    job['pending'] = None
    job['last_error'] = None
    save(path, job)
    print(f'Saved batch {index}/{len(job["chunks"])}.', flush=True)


def run(path, job, timeout):
    if all(c['output'] is not None for c in job['chunks']):
        print('Website batches are already saved. Contextual review and final reread are required before final export.')
        return
    try:
        cli(job, path.parent, 'snapshot')
    except RuntimeError:
        cli(job, path.parent, 'open', 'https://www.humanizeai.pro/', '--headed')
    for c in job['chunks']:
        if c['output'] is not None:
            continue
        if job['pending'] is None:
            if c['attempts'] >= 2:
                raise RuntimeError('Two-submission limit reached for batch ' + str(c['index']))
            payload = base64.b64encode(c['input'].encode('utf-8')).decode('ascii')
            old = code(job, path.parent, READ + """
for (const name of ['Decline', 'Skip']) {
  const b = page.getByRole('button', {name, exact:true});
  if (await b.count() === 1 && await b.isVisible()) await b.click();
}
const text = Buffer.from('""" + payload + """', 'base64').toString('utf8');
await input.fill(text);
if (await input.inputValue() !== text) throw new Error('Input was truncated or changed.');
return {before:await output.inputValue()};
""")
            job['pending'] = {'index': c['index'], 'before': old['before']}
            c['attempts'] += 1
            save(path, job)  # Persist before clicking; a crash must not resubmit.
            code(job, path.parent, READ + "await button.click({timeout:10000}); return {submitted:true};")
            print(f'Submitted batch {c["index"]}/{len(job["chunks"])}.', flush=True)
        pending = job['pending']
        if pending['index'] != c['index']:
            raise RuntimeError('Pending batch does not match next unfinished batch.')
        deadline = time.monotonic() + timeout
        stable = None
        while time.monotonic() < deadline:
            state = code(job, path.parent, POLL)
            if state['input'] != c['input']:
                raise RuntimeError('Browser input differs from pending batch. Inspect the browser before resuming.')
            warning = state['alerts']
            if state['challenge'] or re.search(r'captcha|quota|limit|log.?in|sign.?in|upgrade|payment|too many|try again|error|failed', warning, re.I):
                raise RuntimeError('Website requires attention: ' + (warning or 'Visible CAPTCHA. Complete it in the browser, then resume.'))
            value = state['output'].strip()
            if state['ready'] and value and value != pending['before'].strip():
                if stable == value:
                    accept(path, job, c['index'], value)
                    break
                stable = value
            else:
                stable = None
            time.sleep(2)
        else:
            raise RuntimeError('Timed out waiting for fresh completed output. Pending batch retained; inspect the visible browser before retrying.')
        time.sleep(3)
    print('Website batches saved. Next: review-prepare, contextual review, minimal repairs, final reread, then export.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--input', required=True)
    p.add_argument('--job', required=True)
    p.add_argument('--limit', type=int, default=180)
    for name in ('run', 'status', 'export', 'accept', 'retry', 'review-prepare', 'review-apply', 'review-complete'):
        p = commands.add_parser(name)
        p.add_argument('--job', required=True)
        if name == 'run':
            p.add_argument('--timeout', type=int, default=120)
        if name == 'export':
            p.add_argument('--output', required=True)
        if name in ('accept', 'retry'):
            p.add_argument('--index', type=int, required=True)
        if name == 'accept':
            p.add_argument('--text-file', required=True)
        if name == 'review-apply':
            p.add_argument('--report', required=True)
        if name == 'review-complete':
            p.add_argument('--confirmed-sha256', required=True)
            p.add_argument('--note', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        text = Path(args.input).read_text(encoding='utf-8-sig')
        if not text.strip():
            raise ValueError('Source text is empty.')
        prefix, chunks = split_text(text, args.limit)
        path = Path(args.job).resolve() / 'job.json'
        if path.exists():
            raise ValueError('Job already exists. Resume it or choose a new directory.')
        path.parent.mkdir(parents=True, exist_ok=True)
        job = {'version': 1, 'source_sha256': digest(text), 'source_path': str(Path(args.input).resolve()),
               'limit': args.limit, 'prefix': prefix, 'chunks': chunks,
               'session': 'humanize-' + digest(str(path))[:12], 'pending': None, 'last_error': None, 'review': None}
        save(path, job)
        print(f'Prepared {len(chunks)} batches, at most {args.limit} units each. Job: {path}')
        return
    path, job = load(args.job)
    if args.command == 'run':
        if args.timeout < 1:
            raise ValueError('Timeout must be positive.')
        try:
            run(path, job, args.timeout)
        except (Exception, KeyboardInterrupt) as error:
            job['last_error'] = str(error) or 'Interrupted.'
            save(path, job)
            raise RuntimeError(job['last_error']) from error
    elif args.command == 'status':
        phase = 'website_processing'
        if all(c['output'] is not None for c in job['chunks']):
            phase = 'review_required'
            if job['review'] is not None:
                try:
                    checked_review(path, job)
                    phase = 'review_blocked' if job['review']['unresolved'] else 'final_reread_required'
                    if job['review']['status'] == 'verified':
                        final = checked_review(path, job, require_verified=True)
                        phase = 'ready_to_export'
                        exported = job['review'].get('export_path')
                        if exported and Path(exported).is_file() and read_text_exact(exported) == final:
                            phase = 'complete'
                except (ValueError, OSError, KeyError):
                    phase = 'review_invalid'
        print(json.dumps({'completed': sum(c['output'] is not None for c in job['chunks']),
                          'total': len(job['chunks']), 'pending': job['pending'],
                          'phase': phase, 'workflow_complete': phase == 'complete', 'review': job['review'],
                          'last_error': job['last_error'], 'session': job['session']}, ensure_ascii=False, indent=2))
    elif args.command == 'review-prepare':
        prepare_review(path, job)
    elif args.command == 'review-apply':
        record_review(path, job, args.report)
    elif args.command == 'review-complete':
        finish_review(path, job, args.confirmed_sha256, args.note)
    elif args.command == 'accept':
        accept(path, job, args.index, Path(args.text_file).read_text(encoding='utf-8-sig'))
    elif args.command == 'retry':
        if job['pending'] is None or job['pending']['index'] != args.index:
            raise ValueError('No matching pending batch.')
        if job['chunks'][args.index - 1]['attempts'] >= 2:
            raise ValueError('Two-submission limit reached.')
        job['pending'] = None
        save(path, job)
        print('Pending flag cleared. Rerun only after inspecting the website.')
    elif args.command == 'export':
        final = checked_review(path, job, require_verified=True)
        output = Path(args.output).resolve()
        if output == Path(job['source_path']).resolve():
            raise ValueError('Refusing to overwrite source.')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8', newline='') as stream:
            stream.write(final)
        job['review']['export_path'] = str(output)
        save(path, job)
        print('Exported: ' + str(output))


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('STOPPED: ' + (str(error) or 'Interrupted.'), file=sys.stderr)
        sys.exit(2)
