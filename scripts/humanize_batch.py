#!/usr/bin/env python3
"""HumanizeAI batching with mandatory contextual review and minimal repairs."""
import argparse
import base64
import difflib
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


def split_text(text, limit=200):
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
    job.setdefault('inflight', {})
    job.setdefault('review', None)  # Existing jobs keep website results but need review.
    return path, job


REVIEW_VERSION = 2
REVIEW_CHECKS = ('full_source', 'full_website_output', 'logic_and_causality',
                 'facts_and_meaning', 'global_context_and_boundaries',
                 'omissions_and_references', 'necessary_edits_only',
                 'original_structure_preserved_or_justified', 'source_issues_separated')
CATEGORIES = {'logic', 'fact', 'context', 'omission', 'reference', 'terminology'}


def complete_website(job):
    if any(c['output'] is None for c in job['chunks']):
        raise ValueError('Website processing is incomplete.')
    if job.get('pending') is not None or job.get('inflight'):
        raise ValueError('Pending website requests remain; review/export must wait for resolution.')


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
    template = {'version': REVIEW_VERSION, 'source_sha256': digest(source),
                'website_sha256': digest(raw),
                'checks': {name: False for name in REVIEW_CHECKS},
                'summary': '', 'edits': [], 'unresolved': [],
                'source_notes': [], 'observations': []}
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
    if report.get('version') != REVIEW_VERSION:
        raise ValueError('This review uses an earlier/unsupported policy. Regenerate the review template and review under conservative policy v2; website results are retained.')
    if report.get('source_sha256') != digest(source) or report.get('website_sha256') != digest(raw):
        raise ValueError('Review belongs to a different source or website result.')
    checks = report.get('checks')
    if not isinstance(checks, dict) or any(checks.get(name) is not True for name in REVIEW_CHECKS):
        raise ValueError('Full contextual review checks have not all been confirmed.')
    if not isinstance(report.get('summary'), str) or not report['summary'].strip():
        raise ValueError('A substantive review summary is required, including for zero edits.')
    edits, unresolved = report.get('edits'), report.get('unresolved')
    if not isinstance(edits, list):
        raise ValueError('Edits must be a list.')
    for name in ('unresolved', 'source_notes', 'observations'):
        notes = report.get(name)
        if not isinstance(notes, list) or any(not isinstance(x, str) or not x.strip() for x in notes):
            raise ValueError(f'{name} must be a list of nonempty text findings.')
    located = []
    for number, edit in enumerate(edits, 1):
        if not isinstance(edit, dict) or edit.get('category') not in CATEGORIES:
            raise ValueError(f'Edit {number}: invalid category.')
        for key in ('before', 'after', 'reason', 'evidence', 'reader_impact'):
            if not isinstance(edit.get(key), str):
                raise ValueError(f'Edit {number}: {key} must be text.')
        before, after = edit['before'], edit['after']
        if not before or before == after or any(not edit[k].strip() for k in ('reason', 'evidence', 'reader_impact')):
            raise ValueError(f'Edit {number}: supply a real change, reason, evidence and concrete reader impact.')
        for key in ('introduced_by_website', 'certain_error', 'material_impact', 'necessity_rechecked'):
            if edit.get(key) is not True:
                raise ValueError(f'Edit {number}: {key} must be explicitly confirmed before automatic repair.')
        if type(edit.get('structure_changed')) is not bool:
            raise ValueError(f'Edit {number}: declare whether sentence structure changes.')
        if edit['structure_changed'] and (not isinstance(edit.get('structure_reason'), str) or not edit['structure_reason'].strip()):
            raise ValueError(f'Edit {number}: explain why wording-only repair cannot fix the error.')
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


def change_summary(job, report):
    """Show actual changed spans, excluding unchanged text in locating anchors."""
    raw = merged(job, 'output')
    spans = []
    for number, edit in enumerate(report['edits'], 1):
        start = edit['start'] if 'start' in edit else raw.index(edit['before'])
        matcher = difflib.SequenceMatcher(None, edit['before'], edit['after'], autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != 'equal':
                spans.append({'edit': number, 'raw_start': start + i1, 'raw_end': start + i2,
                              'before': edit['before'][i1:i2], 'after': edit['after'][j1:j2]})
    return {'edit_count': len(report['edits']),
            'removed_characters': sum(len(x['before']) for x in spans),
            'added_characters': sum(len(x['after']) for x in spans),
            'structure_change_count': sum(x['structure_changed'] for x in report['edits']),
            'changed_spans': spans}


def record_review(path, job, report_path):
    report = json.loads(Path(report_path).read_text(encoding='utf-8-sig'))
    final = apply_report(job, report)
    changes = change_summary(job, report)
    folder = path.parent / 'review'
    folder.mkdir(exist_ok=True)
    save(folder / 'report.json', report)
    save(folder / 'change-summary.json', changes)
    write_text_exact(folder / 'corrected-draft.txt', final)
    job['review'] = {'status': 'applied', 'report_version': REVIEW_VERSION,
                     'source_sha256': report['source_sha256'],
                     'website_sha256': report['website_sha256'],
                     'report_sha256': digest(json.dumps(report, ensure_ascii=False, sort_keys=True)),
                     'draft_sha256': digest(final), 'edit_count': len(report['edits']),
                     'change_summary_sha256': digest(json.dumps(changes, ensure_ascii=False, sort_keys=True)),
                     'removed_characters': changes['removed_characters'],
                     'added_characters': changes['added_characters'],
                     'structure_change_count': changes['structure_change_count'],
                     'unresolved': report['unresolved'], 'final_read_note': None}
    save(path, job)
    print(f'Repairs applied: {len(report["edits"])}. Unresolved: {len(report["unresolved"])}.')
    print(f'Actual diff: {changes["removed_characters"]} removed / {changes["added_characters"]} added characters; {changes["structure_change_count"]} declared structure changes. Details: review/change-summary.json')
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
    changes = change_summary(job, report)
    saved_changes = json.loads((folder / 'change-summary.json').read_text(encoding='utf-8-sig'))
    if (review.get('report_version') != REVIEW_VERSION or
            review.get('source_sha256') != report['source_sha256'] or
            review.get('website_sha256') != report['website_sha256'] or
            review.get('report_sha256') != digest(json.dumps(report, ensure_ascii=False, sort_keys=True)) or
            review.get('draft_sha256') != digest(final) or
            read_text_exact(folder / 'corrected-draft.txt') != final or
            review.get('unresolved') != report['unresolved'] or
            saved_changes != changes or
            review.get('change_summary_sha256') != digest(json.dumps(changes, ensure_ascii=False, sort_keys=True))):
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
    if job['pending'] is not None and job['pending']['index'] != index:
        raise ValueError('A different batch is pending; refusing to clear it.')
    if c['output'] is None:
        job['review'] = None
    c['output'] = text.strip()
    job.setdefault('inflight', {}).pop(str(index), None)
    job['pending'] = None
    job['last_error'] = None
    save(path, job)
    print(f'Saved batch {index}/{len(job["chunks"])}.', flush=True)


class BrowserPool:
    """One browser context, isolated page per slot; all writes stay in Python."""
    def __init__(self, path, job):
        self.path, self.job = path, job

    def open(self, slots, recovering):
        try:
            cli(self.job, self.path.parent, 'snapshot')
        except RuntimeError:
            if recovering:
                raise RuntimeError('Pending pages are unavailable. Inspect the browser and pending records; no request was resubmitted.')
            cli(self.job, self.path.parent, 'open', 'https://www.humanizeai.pro/', '--headed')
        code(self.job, self.path.parent, """
const context = page.context();
const needed = """ + str(slots) + """ - context.pages().length;
await Promise.all(Array.from({length:Math.max(0, needed)}, async () => {
  const p = await context.newPage();
  await p.goto('https://www.humanizeai.pro/', {waitUntil:'domcontentloaded', timeout:25000});
}));
return {pages:context.pages().length};
""")

    def fill(self, slot, text):
        payload = base64.b64encode(text.encode('utf-8')).decode('ascii')
        return code(self.job, self.path.parent, """
const p = page.context().pages()[""" + str(slot) + """];
if (!p || p.url() !== 'https://www.humanizeai.pro/') throw new Error('Unexpected pool page.');
for (const name of ['Decline', 'Skip']) {
  const b = p.getByRole('button', {name, exact:true});
  if (await b.count() === 1 && await b.isVisible()) await b.click();
}
const text = Buffer.from('""" + payload + """', 'base64').toString('utf8');
const input = p.getByRole('textbox', {name:'Input Textarea', exact:true});
await input.fill(text);
if (await input.inputValue() !== text) throw new Error('Input was truncated or changed.');
return {before:await p.getByRole('textbox', {name:'Humanized output', exact:true}).inputValue()};
""")

    def submit(self, slots):
        return code(self.job, self.path.parent, """
const slots = """ + str(slots) + """;
return await Promise.all(slots.map(async slot => {
  try {
    await page.context().pages()[slot].getByRole('button', {name:'Humanize AI', exact:true}).click({timeout:10000});
    return {slot, ok:true};
  } catch(e) { return {slot, ok:false, error:String(e)}; }
}));
""")

    def read(self, slots):
        return code(self.job, self.path.parent, """
async function inspect(page) { """ + POLL + """ }
const slots = """ + str(slots) + """;
return await Promise.all(slots.map(async slot => {
  try { return {slot, ...await inspect(page.context().pages()[slot])}; }
  catch(e) { return {slot, error:String(e)}; }
}));
""")


def website_problem(state):
    if state.get('error'):
        return state['error']
    warning = state.get('alerts', '')
    if state.get('challenge') or re.search(r'captcha|quota|limit|log.?in|sign.?in|upgrade|payment|too many|try again|error|failed', warning, re.I):
        return warning or 'Visible CAPTCHA. Complete it in the browser before resuming.'
    return None


def run(path, job, timeout, workers=10):
    if not 1 <= workers <= 10:
        raise ValueError('Workers must be between 1 and 10.')
    active = job.setdefault('inflight', {})
    if job['pending'] is not None:
        old = job['pending']
        if active:
            raise ValueError('Legacy and parallel pending records conflict; inspect before resuming.')
        active[str(old['index'])] = dict(old, slot=0)
        job['pending'] = None
        save(path, job)
    if all(c['output'] is not None for c in job['chunks']):
        if active:
            raise ValueError('Completed job has conflicting pending records.')
        print('Website results saved. Contextual review and final reread are required before export.')
        return
    for key, item in active.items():
        if key != str(item['index']) or not 1 <= item['index'] <= len(job['chunks']) or job['chunks'][item['index'] - 1]['output'] is not None:
            raise ValueError('Invalid pending batch mapping.')
    used = [item['slot'] for item in active.values()]
    if len(set(used)) != len(used) or any(type(s) is not int or s < 0 or s >= 10 for s in used):
        raise ValueError('Invalid or duplicate pending page slot.')
    count = min(workers, sum(c['output'] is None for c in job['chunks']))
    count = max(count, max(used, default=-1) + 1)
    pool = BrowserPool(path, job)
    pool.open(count, bool(active))
    started = {key: time.monotonic() for key in active}
    stable, failures = {}, {}
    job['workers'] = workers
    save(path, job)
    while True:
        if active:
            states = {s['slot']: s for s in pool.read([a['slot'] for a in active.values()])}
            for key, item in list(active.items()):
                if key in failures:
                    continue
                state = states[item['slot']]
                c = job['chunks'][item['index'] - 1]
                problem = website_problem(state)
                if not problem and state['input'] != c['input']:
                    problem = 'Input differs from the mapped batch; inspect the page before resuming.'
                if problem:
                    failures[key] = problem
                    item['error'] = problem
                    save(path, job)
                    continue
                value = state['output'].strip()
                if state['ready'] and value and value != item['before'].strip():
                    if stable.get(key) == value:
                        accept(path, job, c['index'], value)
                        started.pop(key, None)
                        continue
                    stable[key] = value
                else:
                    stable.pop(key, None)
                if time.monotonic() - started[key] > timeout:
                    failures[key] = 'Timed out waiting for fresh stable output; pending request retained.'
                    item['error'] = failures[key]
                    save(path, job)
        # Stop replenishing on the first observed interruption, but save the
        # other requests already in flight before returning control to Codex.
        if failures:
            if all(key in failures for key in active):
                raise RuntimeError('Website processing needs attention: ' + json.dumps(failures, ensure_ascii=False))
        else:
            free = [s for s in range(count) if s not in {a['slot'] for a in active.values()}]
            available = [c for c in job['chunks'] if c['output'] is None and str(c['index']) not in active]
            assignments = list(zip(free[:max(0, workers - len(active))], available))
            newly_prepared = []
            for slot, c in assignments:
                if c['attempts'] >= 2:
                    failures[str(c['index'])] = 'Two-submission limit reached.'
                    break
                old = pool.fill(slot, c['input'])
                key = str(c['index'])
                active[key] = {'index':c['index'], 'slot':slot, 'before':old['before'], 'phase':'prepared'}
                c['attempts'] += 1
                started[key] = time.monotonic()
                newly_prepared.append(slot)
                save(path, job)  # Before any click: an ambiguous crash never resubmits.
            if newly_prepared:
                # All prepared pages are clicked together, rather than waiting
                # for one request to complete before submitting the next.
                outcome = pool.submit(newly_prepared)
                for result in outcome:
                    key = next(k for k,a in active.items() if a['slot'] == result['slot'])
                    active[key]['phase'] = 'submitted' if result['ok'] else 'uncertain'
                    started[key] = time.monotonic()
                    if not result['ok']:
                        failures[key] = result['error']
                        active[key]['error'] = result['error']
                save(path, job)
                print(f'Active requests: {len(active)}/{workers}; saved: {sum(c["output"] is not None for c in job["chunks"])}/{len(job["chunks"])}.', flush=True)
        if failures and not active:
            raise RuntimeError('Website processing needs attention: ' + json.dumps(failures, ensure_ascii=False))
        if not active and all(c['output'] is not None for c in job['chunks']):
            break
        time.sleep(2)
    print('Website batches saved in source order. Next: full contextual review, conservative minimal repairs, final reread and export.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--input', required=True)
    p.add_argument('--job', required=True)
    p.add_argument('--limit', type=int, default=200)
    for name in ('run', 'status', 'export', 'accept', 'retry', 'review-prepare', 'review-apply', 'review-complete'):
        p = commands.add_parser(name)
        p.add_argument('--job', required=True)
        if name == 'run':
            p.add_argument('--timeout', type=int, default=120)
            p.add_argument('--workers', type=int, default=10)
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
    if args.command not in ('run', 'status') and (path.parent / 'run.lock').exists():
        raise ValueError('A runner owns this job. Wait for it to exit before changing task records.')
    if args.command == 'run':
        if args.timeout < 1:
            raise ValueError('Timeout must be positive.')
        lock = path.parent / 'run.lock'
        try:
            with lock.open('x', encoding='utf-8') as stream:
                stream.write(str(os.getpid()))
        except FileExistsError:
            raise ValueError('Job is already locked. Inspect its runner before removing a stale run.lock.')
        try:
            path, job = load(args.job)
            run(path, job, args.timeout, args.workers)
        except (Exception, KeyboardInterrupt) as error:
            job['last_error'] = str(error) or 'Interrupted.'
            save(path, job)
            raise RuntimeError(job['last_error']) from error
        finally:
            lock.unlink(missing_ok=True)
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
                          'inflight': job['inflight'], 'workers': job.get('workers', 10),
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
        legacy = job['pending'] is not None and job['pending']['index'] == args.index
        if not legacy and str(args.index) not in job['inflight']:
            raise ValueError('No matching pending batch.')
        if job['chunks'][args.index - 1]['attempts'] >= 2:
            raise ValueError('Two-submission limit reached.')
        if legacy:
            job['pending'] = None
        job['inflight'].pop(str(args.index), None)
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
