# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lab.test_terminal_installer import TerminalInstallerTests

class IntegrationTests(TerminalInstallerTests):
 def setup_integration(self, home, prefix, data):
  data.mkdir(parents=True)
  current=(prefix/'current').resolve()
  entry=home/'.config/autostart/ember.desktop';entry.parent.mkdir(parents=True)
  entry.write_text('[Desktop Entry]\nX-Ember-Owned=true\nExec=old\n')
  meta=data/'autostart.json';meta.write_text(json.dumps({'steam':str(home/'Steam'),'marker_owned':False,'entry':str(entry),'command':[str(current/'.venv/bin/python'),str(current/'EmberRuntime.py'),'--watch-steam']}))
  return meta,entry
 def test_update_retargets_custom_integration(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);home=root/'home';home.mkdir();prefix=home/'app';source=self.fixture(root)
   m.install(source,prefix,home,self.prepare)
   data=home/'custom-data/ember/Desktop';meta,entry=self.setup_integration(home,prefix,data)
   with patch.dict('os.environ',{'XDG_DATA_HOME':str(home/'custom-data')},clear=False):
    m.install(source,prefix,home,self.prepare)
   command=json.loads(meta.read_text())['command']
   self.assertEqual(command[1],str((prefix/'current').resolve()/'EmberRuntime.py'))
   self.assertIn(command[1],entry.read_text())
 def test_publish_failure_restores_integration(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);home=root/'home';home.mkdir();prefix=home/'app';source=self.fixture(root)
   m.install(source,prefix,home,self.prepare)
   data=home/'.local/share/ember/Desktop';meta,entry=self.setup_integration(home,prefix,data)
   original={p:p.read_bytes() for p in (meta,entry)};write=m.atomic_write
   def fail_marker(path,*args,**kwargs):
    if path.name==m.MARKER and not getattr(fail_marker,'fired',False):
     fail_marker.fired=True;raise OSError('disk error')
    return write(path,*args,**kwargs)
   with patch.object(m,'atomic_write',fail_marker):
    with self.assertRaisesRegex(OSError,'disk error'): m.install(source,prefix,home,self.prepare)
   for p,content in original.items():self.assertEqual(p.read_bytes(),content)
 def test_custom_data_uninstall_runs_cleanup_before_removing_release(self):
  m=self.load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);home=root/'home';home.mkdir();prefix=home/'app';source=self.fixture(root)
   m.install(source,prefix,home,self.prepare)
   data=home/'custom';meta,entry=self.setup_integration(home,prefix,data)
   current=(prefix/'current').resolve();binary=current/'.venv/bin/python'
   binary.write_text('#!/bin/sh\nrm -- '+str(meta)+' '+str(entry)+'\n');binary.chmod(0o755)
   with patch.dict('os.environ',{'EMBER_DATA_DIR':str(data)},clear=False):m.uninstall(prefix,home)
   self.assertFalse(meta.exists());self.assertFalse(entry.exists())
