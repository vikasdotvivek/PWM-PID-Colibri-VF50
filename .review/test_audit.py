import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import audit

class AuditTests(unittest.TestCase):
    def test_python_bare_except(self):
        found = audit.scan_text('code.py', 'try:\n    work()\nexcept:\n    pass\n')
        self.assertEqual({f['rule'] for f in found}, {'bare-except', 'silent-except'})
    def test_python_mutable_default(self):
        found = audit.scan_text('code.py', 'def f(a=[], *, b={}):\n    return a\n')
        self.assertEqual([f['rule'] for f in found], ['mutable-default'])
    def test_python_clean(self):
        self.assertEqual(audit.scan_text('code.py', 'def f(a=None):\n    return [] if a is None else a\n'), [])
    def test_python_legacy(self):
        found = audit.scan_text('code.py', 'print 1\n')
        self.assertEqual(found[0]['rule'], 'python3-parse')
    def test_comment_filter(self):
        text = '// catch {}\n/* Application.DoEvents(); */\ncatch (Exception ex) {}\n'
        found = audit.scan_text('file.cs', text)
        self.assertEqual([(f['rule'], f['line']) for f in found], [('empty-catch', 3)])
    def test_serial(self):
        text = "string t = port.ReadExisting();\nstring[] x = t.Split('#');\n"
        self.assertIn('serial-chunk-split', [f['rule'] for f in audit.scan_text('a.cs', text)])
    def test_arduino(self):
        found = audit.scan_text('read.ino', 'x = map(x, -4.9, 0, 2.5, 0);\n')
        self.assertEqual(found[0]['rule'], 'arduino-map-fractions')
    def test_snapshot_never_executes_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root/'bad.py').write_text('raise RuntimeError("DO NOT EXECUTE")\ndef f(x=[]):\n return x\n')
            (root/'README.md').write_text('docs')
            subprocess.run(['git','-C',str(root),'add','.'],check=True)
            subprocess.run(['git','-C',str(root),'-c','user.name=Audit Test','-c','user.email=audit@example.invalid','commit','-qm','fixture'],check=True)
            report = audit.review(root,'example/repository')
            self.assertEqual(len(report['scanned']),1)
            self.assertEqual(report['total_findings'],1)
            self.assertIn('not a complete manual',audit.markdown(report))
            self.assertIn('/blob/',report['findings'][0]['source'])
            self.assertEqual(json.loads(json.dumps(report))['repository'],'example/repository')
    def test_invalid_repo_name(self):
        self.assertIsNotNone(audit.re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', 'valid/repo'))
        self.assertIsNone(audit.re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', 'invalid/repo\nextra'))

if __name__ == '__main__': unittest.main(verbosity=2)
