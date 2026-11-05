# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import tempfile
import unittest
from pathlib import Path
from ember.library_health import launcher_update, repair_launcher

HEADER = '# Ember native Steam installer (lumalinux)\n'
ORIGINAL = '#!/bin/sh\n' + HEADER + 'if [ -r "module" ]; then\n    export LD_PRELOAD="module"\n    export LUMA_NO_SLS_ACH_UNBLOCK=1\nfi\nexec /usr/bin/steam "$@"\n'

@unittest.skipIf(os.name == 'nt', 'Linux launcher integration')
class LibraryHealthTests(unittest.TestCase):
    def test_repair_preserves_the_launcher_and_byte_exact_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); launcher=root/'steam';launcher.write_text(ORIGINAL);launcher.chmod(0o755)
            backup=repair_launcher(launcher,root/'backups')
            self.assertEqual(Path(backup).read_bytes(), ORIGINAL.encode())
            self.assertEqual(launcher.read_text(), ORIGINAL.replace('    export LUMA_NO_SLS_ACH_UNBLOCK=1\n',''))
            self.assertEqual(launcher.stat().st_mode & 0o777,0o755)
            self.assertIsNone(repair_launcher(launcher,root/'backups'))

    def test_unknown_or_ambiguous_launcher_is_not_rewritten(self):
        self.assertIsNone(launcher_update(ORIGINAL.replace(HEADER,'')))
        self.assertIsNone(launcher_update(ORIGINAL+'export LUMA_NO_SLS_ACH_UNBLOCK=1\n'))
        self.assertIsNone(launcher_update(ORIGINAL.replace('=1','=0')))

    def test_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);real=root/'other';real.write_text(ORIGINAL)
            link=root/'steam';link.symlink_to(real)
            self.assertIsNone(repair_launcher(link,root/'backups'))
            self.assertEqual(real.read_text(),ORIGINAL)

@unittest.skipIf(os.name == 'nt', 'Linux launcher integration')
class LibraryReportTests(unittest.TestCase):
    def report(self, *, repair, snapshot=None, hook='installed', launcher=ORIGINAL, backup=None):
        from contextlib import ExitStack
        from types import SimpleNamespace
        from unittest.mock import patch
        from ember.library_health import run
        with ExitStack() as stack:
            library = stack.enter_context(patch('ember.library_health.Library'))
            library.app_id.side_effect = str
            library.return_value.registrations.return_value = {'42': {}}
            stack.enter_context(patch('ember.library_health._launcher_text', return_value=launcher))
            stack.enter_context(patch('ember.library_health.achievement_hook', return_value=hook))
            writer = stack.enter_context(patch('ember.library_health.repair_launcher', return_value=backup))
            reader = stack.enter_context(patch('ember.library_health.steam_snapshot'))
            if isinstance(snapshot, Exception): reader.side_effect = snapshot
            else: reader.return_value = snapshot or {'minutes':0,'local_last_played':123,'last_played':123,'total':10,'achieved':2}
            result = run(SimpleNamespace(_steam_path=Path('/not-steam')), '42', repair)
            return result, writer.call_count, reader.call_args

    def test_check_never_writes_launcher(self):
        result, writes, read = self.report(repair=False)
        self.assertEqual(writes, 0)
        self.assertFalse(read.kwargs['refresh'])
        self.assertTrue(result['repairable'])

    def test_failed_refresh_is_not_reported_as_success(self):
        result, writes, _ = self.report(repair=True, launcher='unknown', snapshot=RuntimeError('offline'))
        self.assertEqual(writes, 0)
        self.assertIsNone(result['statistics'])
        self.assertFalse(result['repairable'])
        self.assertIn('не завершено', result['message'])

    def test_repair_reports_backup_and_required_restart(self):
        result, writes, _ = self.report(repair=True, hook='disabled', backup='/backup/steam.bak')
        self.assertEqual(writes, 1)
        self.assertTrue(result['restart_required'])
        self.assertEqual(result['backup'], '/backup/steam.bak')

    def test_already_repaired_running_process_does_not_claim_new_write(self):
        result, writes, _ = self.report(repair=True, hook='disabled', launcher=ORIGINAL.replace('    export LUMA_NO_SLS_ACH_UNBLOCK=1\n',''))
        self.assertEqual(writes, 0)
        self.assertTrue(result['restart_required'])
        self.assertNotIn('сохранены', result['message'])
