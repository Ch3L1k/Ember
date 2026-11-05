# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from ember.api_keys import snapshot, save
from sff.core.structs import Settings

class ApiKeysTests(unittest.TestCase):
    def setUp(self):
        self.values = {}
        self.bridge = SimpleNamespace(_api_key='old', _store_client=object(), _hubcap_unavailable=True)
        self.patches = [patch('ember.api_keys.get_setting', side_effect=lambda s: self.values.get(s)),
                        patch('ember.api_keys.set_setting', side_effect=lambda s,v: self.values.__setitem__(s,v)),
                        patch('ember.api_keys.clear_setting', side_effect=lambda s: self.values.pop(s,None))]
        for p in self.patches: p.start(); self.addCleanup(p.stop)

    def test_status_never_returns_the_secret(self):
        self.values[Settings.HUBCAP_KEY]='private-test-key'
        rows = snapshot()
        self.assertEqual(len(rows),6)
        self.assertTrue(next(r for r in rows if r['id']=='morrenus_key')['configured'])
        self.assertNotIn('private-test-key',repr(rows))

    def test_hubcap_replacement_updates_current_client(self):
        self.values[Settings.HUBCAP_KEY_DEAD]=True
        result=save(self.bridge,'morrenus_key',' new-key ')
        self.assertTrue(result['configured'])
        self.assertEqual(self.bridge._api_key,'new-key')
        self.assertIsNone(self.bridge._store_client)
        self.assertFalse(self.bridge._hubcap_unavailable)
        self.assertNotIn(Settings.HUBCAP_KEY_DEAD,self.values)

    def test_delete_affects_only_selected_key(self):
        self.values[Settings.HUBCAP_KEY]='hubcap';self.values[Settings.RYUU_API_KEY]='ryuu'
        result=save(self.bridge,'morrenus_key','')
        self.assertFalse(result['configured'])
        self.assertNotIn(Settings.HUBCAP_KEY,self.values)
        self.assertEqual(self.values[Settings.RYUU_API_KEY],'ryuu')
        self.assertIsNone(self.bridge._api_key)
        self.assertIsNone(self.bridge._store_client)

    def test_unknown_setting_and_control_characters_are_rejected(self):
        for key,value in [('steam_pass','x'),('ryuu_key','abc\ndef'),('ryuu_key','x'*4097)]:
            with self.assertRaises(ValueError): save(self.bridge,key,value)
        self.assertEqual(self.values,{})

    def test_storage_failure_does_not_update_runtime(self):
        with patch('ember.api_keys.set_setting',side_effect=OSError('failure')):
            with self.assertRaises(RuntimeError):save(self.bridge,'morrenus_key','new-key')
        self.assertEqual(self.bridge._api_key,'old')

    def test_ryuu_keys_are_distinct(self):
        save(self.bridge,'ryuu_key','reseller')
        save(self.bridge,'ryuu_api_key','api')
        self.assertEqual(self.values[Settings.RYUU_KEY],'reseller')
        self.assertEqual(self.values[Settings.RYUU_API_KEY],'api')

    def test_manifesthub_key_sets_expiry_and_resets_skip(self):
        from sff.manifest import manifesthub_key
        with patch.object(manifesthub_key,'_skipped_this_session',True):
            with patch('ember.api_keys.time.time',return_value=100):
                save(self.bridge,'manifesthub_api_key','temporary-key')
            self.assertFalse(manifesthub_key._skipped_this_session)
            self.assertEqual(self.values[Settings.MANIFESTHUB_KEY_EXPIRY],str(86500))
            save(self.bridge,'manifesthub_api_key','')
            self.assertNotIn(Settings.MANIFESTHUB_KEY_EXPIRY,self.values)

class SettingsLogTests(unittest.TestCase):
    def test_secret_value_is_not_logged(self):
        from sff.core.storage import settings
        with patch.object(settings,'load_all_settings',return_value={}), patch.object(settings,'keyring_encrypt',return_value=b'ciphertext'), patch.object(settings,'_atomic_write_settings'):
            with self.assertLogs(settings.logger,level='DEBUG') as logs:
                settings.set_setting(Settings.HUBCAP_KEY,'private-test-key')
        self.assertNotIn('private-test-key',' '.join(logs.output))
        self.assertIn('[redacted]',' '.join(logs.output))
