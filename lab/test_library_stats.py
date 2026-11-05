# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import tempfile
import unittest
from pathlib import Path

from ember.host import steam_ui_classes


class LibraryClassesTests(unittest.TestCase):
    def test_playtime_class_comes_from_the_library_module(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'steamui'
            path.mkdir()
            (path / 'sp.js').write_text(
                'a={Playtime:"unrelated"};b={GameStatsSection:"stats",'
                'Playtime:"library-time",GameStat:"stat",GameStatIcon:"icon",MiniAchievements:"achievements"};'
            )
            classes = steam_ui_classes(directory)
            self.assertEqual(classes['Playtime'], 'library-time')
            self.assertEqual(classes['MiniAchievements'], 'achievements')
            self.assertEqual(classes['GameStatIcon'], 'icon')

    def test_missing_playbar_does_not_use_other_module_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'steamui'
            path.mkdir()
            (path / 'sp.js').write_text('a={Playtime:"unrelated"};')
            self.assertNotIn('Playtime', steam_ui_classes(directory))
