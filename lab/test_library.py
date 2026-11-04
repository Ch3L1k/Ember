# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ember.library import Library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = Library(self.root/'Steam', self.root/'Data')
        self.library.plugins.mkdir(parents=True)
        self.lua = self.library.plugins/'900000001.lua'
        self.lua.write_bytes(b'-- Fixture\naddappid(900000001)\n')
        self.installed = [{'app_id':900000001, 'name':'Fixture game', 'installed':True, 'path':str(self.root/'Steam/steamapps/common/Fixture')}]

    def test_snapshot_includes_uninstalled_registrations_and_owned_games_cannot_be_removed(self):
        (self.library.plugins/'900000002.lua').write_text('addappid(900000002)')
        games = self.library.snapshot(self.installed + [{'app_id':900000003,'name':'Owned game','installed':True}], {'900000002':'Waiting game'})
        indexed = {game['app_id']:game for game in games}
        self.assertFalse(indexed['900000002']['installed'])
        self.assertEqual(indexed['900000002']['name'],'Waiting game')
        self.assertFalse(indexed['900000003']['can_remove'])
        with self.assertRaises(ValueError): self.library.remove('900000003','Owned')

    def test_remove_and_restore_preserve_game_files_saves_acf_and_unrelated_registrations(self):
        game = Path(self.installed[0]['path']);game.mkdir(parents=True)
        (game/'game.bin').write_bytes(b'game')
        (game/'save.dat').write_bytes(b'save')
        acf = self.root/'Steam/steamapps/appmanifest_900000001.acf';acf.write_bytes(b'ACF')
        helper = self.library.plugins/'00_LetUpdate_override.lua';helper.write_bytes(b'global')
        other = self.library.plugins/'900000002.lua';other.write_bytes(b'other')
        original = self.lua.read_bytes()
        self.library.remove('900000001','Fixture game')
        self.assertFalse(self.lua.exists())
        self.assertEqual((game/'game.bin').read_bytes(),b'game')
        self.assertEqual((game/'save.dat').read_bytes(),b'save')
        self.assertEqual(acf.read_bytes(),b'ACF')
        self.assertEqual(helper.read_bytes(),b'global')
        self.assertEqual(other.read_bytes(),b'other')
        removed = next(game for game in self.library.snapshot(self.installed) if game['app_id']=='900000001')
        self.assertTrue(removed['removed']);self.assertTrue(removed['can_restore'])
        self.library.restore('900000001')
        self.assertEqual(self.lua.read_bytes(),original)
        self.assertTrue(self.library.snapshot(self.installed)[0]['can_remove'])

    def test_restore_does_not_replace_a_new_registration(self):
        self.library.remove('900000001','Fixture')
        self.lua.write_bytes(b'new registration')
        with self.assertRaisesRegex(ValueError,'существует'): self.library.restore('900000001')
        self.assertEqual(self.lua.read_bytes(),b'new registration')

    def test_corrupt_backup_is_rejected_before_any_restore_writes(self):
        self.library.remove('900000001','Fixture')
        record, _ = self.library.removed()['900000001']
        (record.parent/self.lua.name).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'повреждена'): self.library.restore('900000001')
        self.assertFalse(self.lua.exists())

    def test_nested_registration_helpers_are_archived_together_and_removal_rolls_back_on_failure(self):
        child=self.library.plugins/'900000001';child.mkdir()
        (child/'00_LetUpdate_override.lua').write_bytes(b'addappid(900000001)')
        original_unlink=Path.unlink
        def fail_second(file,*args,**kwargs):
            if file.parent==child: raise PermissionError('fixture locked file')
            return original_unlink(file,*args,**kwargs)
        with patch.object(Path,'unlink',fail_second):
            with self.assertRaises(PermissionError): self.library.remove('900000001','Fixture')
        self.assertTrue(self.lua.exists())
        self.library.remove('900000001','Fixture')
        self.assertFalse((child/'00_LetUpdate_override.lua').exists())
        self.library.restore('900000001')
        self.assertEqual((child/'00_LetUpdate_override.lua').read_bytes(),b'addappid(900000001)')

    def test_invalid_app_ids_are_rejected(self):
        for value in ('../900000001','0','01','９','4294967296',''):
            with self.assertRaises(ValueError): self.library.remove(value,'Invalid')
        self.assertTrue(self.lua.exists())


if __name__=='__main__': unittest.main()
