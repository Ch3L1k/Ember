# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

class BootstrapTests(unittest.TestCase):
 def load(self):
  path=Path(__file__).resolve().parents[1]/'packaging/bootstrap.py'
  self.assertTrue(path.exists(),'Archive verifier not implemented')
  spec=importlib.util.spec_from_file_location('ember_bootstrap',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def test_archive_extracts_expected_installer(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);archive=root/'source.zip'
   with zipfile.ZipFile(archive,'w') as z:z.writestr('Ember/install.sh','echo ready');z.writestr('Ember/packaging/terminal_installer.py','# code')
   m.extract(archive,root/'out')
   self.assertEqual((root/'out/Ember/install.sh').read_text(),'echo ready')
 def test_archive_traversal_rejected_before_writing(self):
  m=self.load()
  for name in ('../escape','/absolute','Ember/../../escape','other/install.sh','Ember/../escape','Ember/..\\escape'):
   with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);archive=root/'source.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'bad')
    with self.assertRaises(ValueError):m.extract(archive,root/'out')
    self.assertFalse((root/'out').exists())
 def test_bad_checksum_rejected(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);file=root/'Ember-Source.zip';file.write_bytes(b'changed')
   with self.assertRaises(ValueError):m.verify(file,'0'*64+'  Ember-Source.zip\n')
