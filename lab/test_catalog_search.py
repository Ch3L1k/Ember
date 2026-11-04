# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ember.catalog_search import CatalogIndex

class CatalogTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.rows=[{'appid':i,'name':f'Test Game {i:02}'} for i in range(1,51)]
  self.rows += [{'appid':80,'name':'Grand Theft Auto: San Andreas'}, {'appid':81,'name':'Adult Test Game','nsfw':True}]
  (self.root/'games.json').write_text(json.dumps(self.rows))
  self.index=CatalogIndex([self.root])
 def test_local_search_never_uses_network(self):
  with patch('urllib.request.urlopen',side_effect=AssertionError('network')):
   result=self.index.search('test',0,20,block_nsfw=True)
  self.assertEqual(len(result['games']),20);self.assertEqual(result['total'],50)
 def test_pages_have_no_double_offset_or_duplicates(self):
  a=self.index.search('test',0,20,block_nsfw=True);b=self.index.search('test',20,20,block_nsfw=True)
  self.assertEqual(len(b['games']),20)
  self.assertFalse({x['app_id'] for x in a['games']} & {x['app_id'] for x in b['games']})
 def test_alias_and_numeric_id(self):
  self.assertEqual(self.index.search('gta san andreas',0,20)['games'][0]['app_id'],80)
  self.assertEqual(self.index.search('80',0,20)['games'][0]['app_id'],80)
 def test_corrupt_optional_source_does_not_break_catalog(self):
  (self.root/'games_appid.json').write_text('{broken')
  self.assertGreater(self.index.search('test',0,20)['total'],0)
 def test_remote_merge_deduplicates_before_pagination(self):
  self.index.merge([{'app_id':1,'name':'Test Game 01','status':'available'}, {'app_id':90,'name':'Test Game 90'}])
  result=self.index.search('test',0,100,block_nsfw=True)
  self.assertEqual(result['total'],51);self.assertEqual(len({x['app_id'] for x in result['games']}),51)
 def test_cache_metadata_cannot_override_appid(self):
  self.index.merge([{'app_id':'../escape','name':'Test'}])
  self.assertEqual(self.index.search('../escape',0,20)['total'],0)
 def test_filters_apply_before_offset(self):
  self.index.merge([{'app_id':2,'name':'Test Game 02','tags':['Action']}])
  result=self.index.search('test',0,20,tag='Action')
  self.assertEqual(result['total'],1);self.assertEqual(result['games'][0]['app_id'],2)

class CatalogSchedulingTests(unittest.TestCase):
 def test_latest_local_search_does_not_wait_for_remote_enrichment(self):
  from ember.catalog_search import search
  from types import SimpleNamespace
  jobs=[];events=[]
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'games.json').write_text(json.dumps([{'appid':1,'name':'Alpha'},{'appid':2,'name':'Beta'}]))
   index=CatalogIndex([root])
   bridge=SimpleNamespace(_ember_catalog=index,_run_async=lambda fn,**kw:jobs.append((fn,kw)),
    search_results=SimpleNamespace(emit=lambda raw:events.append(json.loads(raw))),task_finished=SimpleNamespace(emit=lambda raw:None),_get_store_client=lambda:None)
   with patch('sff.gui.bridges.store_bridge._store_blocks_nsfw',return_value=False):
    search(bridge,'Alpha',0,20,'updated','','old')
    fn,callbacks=jobs.pop(0);callbacks['on_done'](fn())
    self.assertEqual(events[0]['games'][0]['name'],'Alpha')
    # Leave the network worker queued (as if it is indefinitely stalled).
    self.assertEqual(len(jobs),1)
    search(bridge,'Beta',0,20,'updated','','new')
    fn,callbacks=jobs.pop();callbacks['on_done'](fn())
    self.assertEqual(events[-1]['request_id'],'new')
    self.assertEqual(events[-1]['games'][0]['name'],'Beta')
 def test_obsolete_local_result_is_not_published(self):
  from ember.catalog_search import search
  from types import SimpleNamespace
  jobs=[];events=[]
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'games.json').write_text('[]')
   bridge=SimpleNamespace(_ember_catalog=CatalogIndex([root]),_run_async=lambda fn,**kw:jobs.append((fn,kw)),search_results=SimpleNamespace(emit=lambda raw:events.append(json.loads(raw))))
   with patch('sff.gui.bridges.store_bridge._store_blocks_nsfw',return_value=False):
    search(bridge,'Old',0,20,'updated','','old');search(bridge,'New',0,20,'updated','','new')
    fn,callbacks=jobs.pop(0);callbacks['on_done'](fn())
    self.assertEqual(events,[])
    self.assertEqual(bridge._ember_catalog_current[-1],'new')
 def test_remote_supplement_survives_restart(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory);index=CatalogIndex([path],path/'extra.json')
   index.persist([{'app_id':480,'name':'Spacewar'}])
   self.assertEqual(CatalogIndex([path],path/'extra.json').search('spacewar',0,20)['total'],1)
 def test_steam_classification_is_preserved_on_restart(self):
  from ember.catalog_search import _queue_enrichment
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'games.json').write_text(json.dumps([{'appid':480,'name':'Quiet Puzzle'}]))
   index=CatalogIndex([root],root/'extra.json');jobs=[]
   request=('quiet',0,20,'updated','','one')
   bridge=SimpleNamespace(_ember_catalog_current=request,_get_store_client=lambda:None,
    _run_async=lambda fn,**kw:jobs.append((fn,kw)),task_finished=SimpleNamespace(emit=lambda raw:None))
   _queue_enrichment(bridge,index,request,False)
   with patch.object(index,'refresh'),patch('sff.gui.bridges.store_bridge._fetch_steam_image_urls',return_value=({}, {}, {480:True})):
    fn,callbacks=jobs.pop();callbacks['on_done'](fn())
   restarted=CatalogIndex([root],root/'extra.json')
   self.assertEqual(restarted.search('quiet',0,20,block_nsfw=True)['total'],0)

class CatalogWindowsEncodingTests(unittest.TestCase):
 def test_utf8_titles_survive_a_windows_ansi_default_encoding(self):
  original = Path.read_text
  def ansi_default(path, encoding=None, errors=None, **kwargs):
   return original(path, encoding=encoding or 'cp1252', errors=errors, **kwargs)
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   (root/'games.json').write_text(json.dumps([{'app_id':123,'name':'Тестовая игра'}],ensure_ascii=False),encoding='utf-8')
   with patch.object(Path,'read_text',ansi_default):
    result=CatalogIndex([root]).search('Тестовая',0,20)
   self.assertEqual(result['total'],1)
   self.assertEqual(result['games'][0]['name'],'Тестовая игра')
