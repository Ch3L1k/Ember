# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import yaml
from ember.library import Library
from ember.linux_registration import write_native_keys

class MetadataTransactions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  for patcher in [patch.dict('os.environ',XDG_CONFIG_HOME=str(self.root/'config'),EMBER_MODE='desktop'),patch('ember.config.DATA',self.root/'data'),patch('ember.linux_tools.DATA',self.root/'data')]:
   patcher.start();self.addCleanup(patcher.stop)
  self.cfg=self.root/'config/SLSsteam/config.yaml';self.cfg.parent.mkdir(parents=True);self.cfg.write_text('AdditionalApps: [480]\n')
  self.keys=self.root/'config/lumalinux/keys.txt';self.keys.parent.mkdir(parents=True);self.keys.write_text('480;\n481;480;0;0;'+'a'*64+'\n')
  self.lib=Library(self.root/'Steam',self.root/'data');self.lib.plugins.mkdir(parents=True);self.lua=self.lib.plugins/'480.lua';self.lua.write_text('addappid(480)')
 def test_remove_failure_restores_sls_registration(self):
  with patch('ember.linux_registration.restore_native_entries',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):self.lib.remove('480','Fixture')
  self.assertEqual(yaml.safe_load(self.cfg.read_text())['AdditionalApps'],[480]);self.assertTrue(self.lua.exists())
 def test_restore_failure_restores_removed_state(self):
  self.lib.remove('480','Fixture')
  with patch('ember.linux_registration.restore_native_entries',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):self.lib.restore('480')
  self.assertFalse(yaml.safe_load(self.cfg.read_text())['AdditionalApps']);self.assertFalse(self.lua.exists())
 def test_concurrent_native_metadata_writes_keep_every_registration(self):
  values=[SimpleNamespace(app_id=i,depots=[],manifest_overrides={}) for i in range(500,520)]
  with ThreadPoolExecutor(max_workers=8) as pool:
   list(pool.map(write_native_keys,values))
  lines=self.keys.read_text().splitlines()
  for i in range(500,520):self.assertIn(str(i)+';',lines)
  self.assertIn('480;',lines)
