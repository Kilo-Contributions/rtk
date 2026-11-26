"""RTK returns UTF-8 even when the Hermes host's preferred codec differs."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

PLUGIN = Path(__file__).resolve().parents[1] / 'rtk-rewrite' / '__init__.py'


class RewriteEncodingTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('rtk_encoding_test_plugin', PLUGIN)
        self.plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.plugin)

    def rewrite(self, raw, exit_code=0):
        # Use a real child process emitting bytes; emulate a legacy Windows
        # preferred codec only when the adapter fails to specify its encoding.
        real_run = subprocess.run
        calls = []

        def child(argv, **kwargs):
            self.assertEqual(argv[:2], ['rtk', 'rewrite'])
            calls.append(kwargs.copy())
            kwargs.setdefault('encoding', 'cp1252')
            return real_run([sys.executable, '-c',
                             f'import sys; sys.stdout.buffer.write({raw!r}); sys.exit({exit_code})'],
                            **kwargs)

        args = {'command': 'git status', 'workdir': 'unused'}
        with mock.patch.object(self.plugin.subprocess, 'run', side_effect=child):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertIsNone(self.plugin._pre_tool_call(tool_name='terminal', args=args))
        self.assertEqual(len(calls), 1)
        return args['command'], calls[0], stderr.getvalue()

    def test_non_ascii_rewrite_is_exact(self):
        command = 'rtk git -C "C:/工程/é 🎮" status'
        actual, kwargs, warning = self.rewrite((command + '\n').encode('utf-8'))
        self.assertEqual(actual, command)
        self.assertEqual(kwargs['encoding'], 'utf-8')
        self.assertEqual(warning, '')

    def test_invalid_utf8_preserves_original_command(self):
        actual, _, warning = self.rewrite(b'rtk git status\xff\n')
        self.assertEqual(actual, 'git status')
        self.assertIn('rtk: hermes plugin warning:', warning)

    def test_existing_return_codes_unchanged(self):
        for code in (0, 1, 2, 3, 4):
            with self.subTest(code=code):
                actual, _, warning = self.rewrite(b'rtk git status\n', code)
                self.assertEqual(actual, 'rtk git status' if code in (0, 3) else 'git status')
                if code != 4:
                    self.assertEqual(warning, '')


if __name__ == '__main__':
    unittest.main()
