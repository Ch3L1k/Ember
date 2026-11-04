# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run platform-appropriate tests with isolated application data."""
import os
from pathlib import Path
import tempfile
import unittest

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='ember-tests-') as folder:
        root = Path(folder)
        for name in ('data', 'config', 'cache', 'localappdata'):
            (root / name).mkdir()
        os.environ.update(EMBER_DATA_DIR=str(root/'data'), XDG_DATA_HOME=str(root/'data'),
            XDG_CONFIG_HOME=str(root/'config'), XDG_CACHE_HOME=str(root/'cache'),
            LOCALAPPDATA=str(root/'localappdata'), QT_QPA_PLATFORM='offscreen')
        from PyQt6 import QtWebEngineWidgets
        tests = []
        linux_only = {'test_linux', 'test_linux_registration', 'test_diagnostics', 'test_metadata_transactions',
                      'test_terminal_installer', 'test_terminal_integration', 'test_installer_progress'}
        for path in sorted(Path(__file__).parent.glob('test_*.py')):
            if os.name == 'nt' and path.stem in linux_only:
                continue
            tests.append('lab.' + path.stem)
        suite = unittest.defaultTestLoader.loadTestsFromNames(tests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
