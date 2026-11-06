#!/usr/bin/env python3
"""Read-only source triage. Never imports, builds, or runs repository code."""
import argparse
import ast
import collections
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

VERSION = '1.0'
MAX_BYTES = 1_000_000
MAX_FINDINGS = 2000
CODE = {'.py', '.cs', '.cpp', '.cc', '.c', '.h', '.hpp', '.ino', '.js', '.ts',
        '.tsx', '.jsx', '.rs', '.go', '.java', '.sh', '.bash', '.cmake'}
EXCLUDED = {'.git', '.review', 'node_modules', 'build', 'install', 'log', 'dist',
            'bin', 'obj', '__pycache__', '.venv', 'venv', 'vendor', 'third_party'}
MANIFESTS = {'CMakeLists.txt', 'package.xml', 'package.json', 'pyproject.toml',
             'requirements.txt', 'setup.py', 'Cargo.toml', 'go.mod', 'Makefile',
             'platformio.ini', 'arduino-cli.yaml'}
C_LEX = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/', re.S)
RULES = [
    ('empty-catch', 'P2', r'\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}',
     'Empty catch discards an exception',
     'Handle expected failures explicitly and preserve diagnostics; define the fault response before changing hardware behavior.'),
    ('ui-reentrancy', 'P2', r'\bApplication(?:::|\.)DoEvents\s*\(',
     'Nested UI event pumping',
     'Check for reentrant start/stop handlers; separate acquisition from UI work and test cancellation.'),
    ('callback-count-clock', 'P2', r'\b(?:Ticks|LapsedCount|ScanInterval\s*\*\s*DataSno)\s*/\s*\d+',
     'Elapsed time appears derived from callback counts',
     'Measure elapsed time independently and test delayed callbacks. Validate the device clock against an external reference.'),
    ('serial-chunk-split', 'P1', r'ReadExisting\(\);[\s\S]{0,260}?\bSplit\s*\(',
     'Serial read appears split before frame reconstruction',
     'Inspect the surrounding parser; test partial, combined, malformed and oversized frames before replacing the wire protocol.'),
    ('blocking-ui-sleep', 'P2', r'(?:Thread(?:::|\.)Sleep|Thread::Sleep)\s*\(\s*(?:[1-9]\d{2,})\s*\)',
     'Long blocking sleep; inspect calling thread',
     'Determine whether this blocks a UI/control callback. Replace with an interruptible deadline only after reviewing control semantics.'),
]


def without_comments(text):
    def replace(match):
        value = match.group(0)
        if value.startswith('//') or value.startswith('/*'):
            return ''.join('\n' if c == '\n' else ' ' for c in value)
        return value
    return C_LEX.sub(replace, text)


def scan_text(path, text):
    findings = []
    def add(rule, priority, line, title, recommendation):
        findings.append(dict(rule=rule, priority=priority, path=path,
                             line=max(1, line), title=title,
                             recommendation=recommendation, status='review-required'))
    suffix = Path(path).suffix.lower()
    if suffix == '.py':
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError as error:
            add('python3-parse', 'P1', error.lineno or 1, 'Does not parse with the audit runner Python 3',
                'Confirm the intended Python version. This may be legacy Python 2 rather than an unintended syntax error; compile with the supported interpreter.')
            return findings
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    add('bare-except', 'P2', node.lineno, 'Bare except also catches interruption/exit',
                        'Catch the expected exception class and test cancellation; retain useful diagnostics.')
                if all(isinstance(s, ast.Pass) for s in node.body):
                    add('silent-except', 'P2', node.lineno, 'Exception handler only passes',
                        'Decide whether the error is recoverable; surface nonrecoverable failures instead of silently continuing.')
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
                if any(isinstance(d, (ast.List, ast.Dict, ast.Set)) for d in defaults):
                    add('mutable-default', 'P2', node.lineno, 'Mutable literal used as a function default',
                        'Use None and allocate per call unless shared state is intentional; test two independent calls.')
            if isinstance(node, ast.Call):
                name = getattr(node.func, 'id', '')
                if name in {'eval', 'exec'}:
                    add('dynamic-code', 'P2', node.lineno, 'Dynamic code execution needs a trust boundary',
                        'Trace the input source; prefer structured parsing for untrusted data and test malformed input.')
                if any(k.arg == 'shell' and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                    add('shell-command', 'P2', node.lineno, 'shell=True invocation needs input review',
                        'Prefer an argument list where possible; never interpolate untrusted input into a shell command.')
        return findings
    clean = without_comments(text)
    if suffix in {'.cs', '.cpp', '.cc', '.c', '.h', '.hpp', '.ino', '.txt'}:
        for rule, priority, expression, title, recommendation in RULES:
            for match in re.finditer(expression, clean):
                add(rule, priority, clean.count('\n', 0, match.start()) + 1, title, recommendation)
        if suffix == '.ino':
            for match in re.finditer(r'\bmap\([^;\n]*\d+\.\d+[^;\n]*\)', clean):
                add('arduino-map-fractions', 'P1', clean.count('\n', 0, match.start()) + 1,
                    'Fractional arguments passed to Arduino integer map',
                    'Verify the active map overload and physical units; test floating-point interpolation endpoints and midpoint before altering calibration.')
    return findings


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], timeout=30)


def review(root, repository):
    revision = git(root, 'rev-parse', 'HEAD').decode().strip()
    files = [p for p in git(root, 'ls-files', '-z').decode('utf-8', 'surrogateescape').split('\0') if p]
    scanned, skipped, findings, manifests, tests = [], [], [], [], []
    for name in sorted(files):
        rel = Path(name)
        if any(part in EXCLUDED for part in rel.parts) or name.endswith('.Designer.cs'):
            skipped.append(dict(path=name, reason='generated/vendor/review path')); continue
        if rel.name in MANIFESTS or rel.suffix.lower() in {'.csproj', '.vcproj', '.vcxproj', '.sln'}:
            manifests.append(name)
        if re.search(r'(^|/)(tests?|test_[^/]*)(/|\.)|(_test\.|\.spec\.|\.test\.)', name, re.I):
            tests.append(name)
        full = root / rel
        if full.is_symlink() or not full.is_file():
            skipped.append(dict(path=name, reason='symlink/submodule/nonregular')); continue
        if full.stat().st_size > MAX_BYTES:
            skipped.append(dict(path=name, reason='over 1000000 bytes')); continue
        is_code = rel.suffix.lower() in CODE or rel.name in {'CMakeLists.txt', 'Makefile'}
        is_snippet = rel.suffix.lower() == '.txt' and 'example' in rel.name.lower()
        if not is_code and not is_snippet:
            skipped.append(dict(path=name, reason='non-source format; content not audited')); continue
        raw = full.read_bytes()
        if b'\0' in raw:
            skipped.append(dict(path=name, reason='binary')); continue
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            skipped.append(dict(path=name, reason='non-UTF8; manual encoding review needed')); continue
        scanned.append(dict(path=name, lines=len(text.splitlines()), bytes=len(raw)))
        findings.extend(scan_text(name, text))
    findings.sort(key=lambda f: (f['priority'], f['path'], f['line'], f['rule']))
    total_findings = len(findings)
    findings = findings[:MAX_FINDINGS]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid repository identifier')
    for item in findings:
        item['source'] = f'https://github.com/{repository}/blob/{revision}/{quote(item["path"], safe="/")}#L{item["line"]}'
    return dict(generator='repository-static-triage', version=VERSION, repository=repository,
                revision=revision, tracked_files=len(files), scanned=scanned, skipped=skipped,
                manifests=manifests, conventional_test_paths=tests, findings=findings,
                total_findings=total_findings, findings_omitted=total_findings-len(findings),
                execution='No repository code, tests, builds or hardware were executed.')


def markdown(report):
    counts = collections.Counter(f['priority'] for f in report['findings'])
    lines = ['# Code improvement triage', '',
             '**Automated first pass, not a complete manual code audit or a safety certification.**', '',
             f'Repository: `{report["repository"]}`', f'Snapshot: `{report["revision"]}`', '',
             f'- Tracked paths: {report["tracked_files"]}; source files inspected: {len(report["scanned"])}.',
             f'- Findings: {report["total_findings"]}; retained: {len(report["findings"])}; omitted by cap: {report["findings_omitted"]}.',
             f'- Priority counts in retained findings: {dict(counts)}.',
             f'- {report["execution"]}', '',
             '## Scope and limitations', '',
             'Python findings use AST parsing under the runner Python 3. C/C++/C# findings are lexical review candidates, not compiler-verified defects. Files over 1 MB, designer files, generated/vendor paths, binaries, notebooks, PDFs and other non-source formats are excluded and enumerated in the JSON report. No findings does not establish correctness.', '',
             '## Build and test follow-up', '']
    if report['manifests']:
        lines += ['Build/dependency entry points detected:'] + ['- `' + p.replace('`', '') + '`' for p in report['manifests'][:20]]
        if len(report['manifests']) > 20: lines += ['Additional entry points are listed in JSON.']
    else:
        lines += ['No conventional build/dependency manifest was detected outside excluded paths. Document the intended compiler/runtime, dependencies, and a reproducible build command; this may be an intentionally partial source archive.']
    lines += ['', ('Conventional test paths were detected; review their coverage and run the documented suite in the proper environment.' if report['conventional_test_paths'] else 'No conventional test paths were detected. Add regression fixtures for the critical calculations and input boundaries; notebook/manual tests may still exist.'), '', '## Potential improvements', '']
    for i, item in enumerate(report['findings'][:100], 1):
        lines += [f'### {i}. {item["priority"]}: {item["title"]}',
                  f'Source: [{item["path"].replace("`", "")}:{item["line"]}]({item["source"]})',
                  item['recommendation'], '']
    if not report['findings']:
        lines += ['No matches from this limited rule set. Inspect architecture, algorithm correctness, tests and deployment assumptions manually before accepting changes.', '']
    elif len(report['findings']) > 100:
        lines += ['The Markdown report shows the first 100 findings; the JSON contains additional retained candidates.', '']
    lines += ['## Acceptance gate', '',
              'Confirm each candidate in its calling context. Add a regression test, make one focused change, and build using the actual target dependencies. For robotics/actuator firmware, verify safe outputs, limit handling, sensor failure and timing on a controlled test rig. Do not merge or deploy a blanket rewrite based on these pattern matches.', '',
              'Machine-readable scope, exclusions and findings: `static-review.json`.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    report = review(root, args.repository)
    output = root / '.review'
    if output.is_symlink(): raise ValueError('Refusing symlink output directory')
    output.mkdir(exist_ok=True)
    for filename in ('STATIC_REVIEW.md', 'static-review.json'):
        if (output / filename).is_symlink(): raise ValueError('Refusing symlink output file')
    (output / 'STATIC_REVIEW.md').write_text(markdown(report), encoding='utf-8')
    (output / 'static-review.json').write_text(json.dumps(report, indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('repository', 'revision', 'tracked_files', 'total_findings')}))
    print('Inspected source files:', len(report['scanned']), '; excluded paths:', len(report['skipped']))


if __name__ == '__main__':
    main()
