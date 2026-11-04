# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from ember.platform_selection import required_platform

class PlatformSelectionTests(unittest.TestCase):
    def info(self):
        return {'common': {'oslist': 'windows,linux,macos'}, 'depots': {
            '101': {'config': {'oslist': 'windows'}, 'manifests': {'public': {'gid': '1'}}},
            '102': {'config': {'oslist': 'linux'}, 'manifests': {'public': {'gid': '2'}}},
            '103': {'config': {'oslist': 'macos'}, 'manifests': {'public': {'gid': '3'}}},
            '228989': {'depotfromapp': '228980', 'config': {'oslist': 'windows'}},
        }}

    def test_windows_source_requires_proton_despite_linux_store_support(self):
        self.assertEqual(required_platform(self.info(), {'101', '228989'}), 'windows')

    def test_native_content_is_preferred_when_present(self):
        self.assertEqual(required_platform(self.info(), {'101', '102'}), 'both')

    def test_common_content_can_run_on_linux(self):
        info=self.info(); info['depots']['102']['config']={}
        self.assertEqual(required_platform(info, {'102'}), 'both')

    def test_redist_or_workshop_id_is_not_game_content(self):
        for ids in ({'228989'}, {'999'}):
            with self.assertRaises(ValueError): required_platform(self.info(), ids)

    def test_mac_only_data_is_rejected(self):
        with self.assertRaises(ValueError): required_platform(self.info(), {'103'})

    def test_missing_metadata_does_not_claim_compatibility(self):
        with self.assertRaises(ValueError): required_platform({}, {'101'})

class CompatibilitySelectionTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.data=patch('ember.config.DATA', Path(self.temp.name)); self.data.start(); self.addCleanup(self.data.stop)

    def client(self, *states):
        from unittest.mock import Mock
        client=Mock()
        client.call.side_effect=[{'result': {'value': s}} for s in states]
        return client

    def test_native_selection_changes_to_proton_and_is_verified(self):
        from ember.platform_selection import configure_platform
        c=self.client({'tool':'steamlinuxruntime_4','priority':90}, {'tool':'proton-stable','priority':250})
        self.assertEqual(configure_platform(123,'windows',c)['tool'], 'proton-stable')
        c.evaluate.assert_called_once_with('SteamClient.Apps.SpecifyCompatTool(123, "proton-stable")')

    def test_existing_custom_proton_is_preserved(self):
        from ember.platform_selection import configure_platform
        c=self.client({'tool':'GE-Proton11-11','priority':250})
        configure_platform(123,'windows',c); c.evaluate.assert_not_called()

    def test_both_platforms_do_not_override_user_choice(self):
        from ember.platform_selection import configure_platform
        c=self.client(); configure_platform(123,'both',c)
        c.evaluate.assert_not_called(); c.call.assert_not_called()

    def test_native_only_source_does_not_silently_keep_proton(self):
        from ember.platform_selection import configure_platform
        c=self.client({'tool':'proton-stable','priority':250})
        with self.assertRaises(ValueError): configure_platform(123,'linux',c)
        c.evaluate.assert_not_called()

    def test_failed_confirmation_restores_default(self):
        from ember.platform_selection import configure_platform
        c=self.client({'tool':'steamlinuxruntime_4','priority':90})
        c.call.side_effect=[{'result':{'value':{'tool':'steamlinuxruntime_4','priority':90}}}, RuntimeError('disconnected')]
        with self.assertRaises(RuntimeError): configure_platform(123,'windows',c)
        self.assertEqual(c.evaluate.call_args.args[0], 'SteamClient.Apps.SpecifyCompatTool(123, "")')

class PrefixPreparationTests(unittest.TestCase):
    def test_all_libraries_are_prepared_before_steam_chooses_install_location(self):
        from pathlib import Path
        from unittest.mock import patch, call
        from ember.platform_selection import prepare_registration_prefixes
        with patch('sff.core.storage.vdf.get_steam_libs', return_value=[Path('/steam'), Path('/games')]), patch('ember.host.prepare_compatdata') as prepare:
            prepare_registration_prefixes('/steam', '123')
        self.assertEqual(prepare.call_args_list, [call('/steam', Path('/steam'), '123'), call('/steam', Path('/games'), '123')])

    def test_prefix_failure_is_not_silently_ignored(self):
        from unittest.mock import patch
        from ember.platform_selection import prepare_registration_prefixes
        with patch('sff.core.storage.vdf.get_steam_libs', return_value=['/games']), patch('ember.host.prepare_compatdata', side_effect=OSError('read only')):
            with self.assertRaises(OSError): prepare_registration_prefixes('/steam', '123')

if __name__=='__main__': unittest.main()
