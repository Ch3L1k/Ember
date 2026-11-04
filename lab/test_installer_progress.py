# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

class InstallerProgressTests(unittest.TestCase):
 def load(self):
  spec=importlib.util.spec_from_file_location('installer',Path(__file__).resolve().parents[1]/'packaging/terminal_installer.py')
  m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertTrue(hasattr(m,'run_logged'),'Logged subprocess runner not implemented')
  return m
 def test_success_keeps_full_log(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);log=root/'install.log'
   m.run_logged([sys.executable,'-c','print("dependency ready")'],root,log,'Test')
   self.assertIn('dependency ready',log.read_text())
 def test_failed_command_reports_log_and_preserves_output(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);log=root/'install.log'
   with self.assertRaisesRegex(RuntimeError,'install.log'):
    m.run_logged([sys.executable,'-c','print("missing dependency"); raise SystemExit(3)'],root,log,'Test')
   self.assertIn('missing dependency',log.read_text())
