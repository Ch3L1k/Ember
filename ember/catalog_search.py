# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software under the GNU General Public License,
# version 3 or later. Distributed WITHOUT ANY WARRANTY. See LICENSE.

from collections import OrderedDict
import json
import logging
import os
import tempfile
from pathlib import Path
import threading
import time

logger = logging.getLogger(__name__)


class CatalogIndex:
    def __init__(self, directories, extra_file=None):
        self.directories = list(map(Path, directories))
        self.extra_file = Path(extra_file) if extra_file else None
        self.rows = {}
        self.lock = threading.RLock()
        self.loaded = False
        self.cache = OrderedDict()

    def load(self):
        with self.lock:
            if self.loaded:
                return
            for directory in reversed(self.directories):
                for name in ('games_appid.json', 'software_appid.json', 'games.json'):
                    path = directory/name
                    if not path.is_file():
                        continue
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        if isinstance(payload, dict):
                            payload = [dict(v, app_id=k) if isinstance(v, dict) else {'app_id': k, 'name': v} for k, v in payload.items()]
                        if isinstance(payload, list):
                            self._merge(payload)
                    except (OSError, ValueError, TypeError):
                        logger.warning('Catalog cache could not be read: %s', path, exc_info=True)
            if self.extra_file and self.extra_file.is_file():
                try:
                    self._merge(json.loads(self.extra_file.read_text(encoding="utf-8")))
                except (OSError, ValueError, TypeError):
                    logger.warning('Catalog supplemental cache invalid', exc_info=True)
            self.loaded = True
            logger.info('Local catalog indexed: %s apps', len(self.rows))

    def _merge(self, rows):
        from sff.gui.bridges.store_bridge import _normalize_for_search
        if not isinstance(rows, list):
            return
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            appid = str(raw.get('app_id') or raw.get('appid') or '')
            if not appid.isascii() or not appid.isdigit() or not 0 < int(appid) <= 4294967295:
                continue
            aid = int(appid)
            name = raw.get('name') or self.rows.get(aid, {}).get('name')
            if not isinstance(name, str) or not name.strip():
                continue
            row = dict(self.rows.get(aid, {}))
            for key in ('name', 'tags', 'nsfw', 'drm', 'header_image', 'image_url', 'status', 'size', 'source', 'last_updated', 'type'):
                if key in raw:
                    row[key] = raw[key]
            row.update(app_id=aid, name=name, norm=_normalize_for_search(name))
            self.rows[aid] = row
        self.cache.clear()

    def merge(self, rows):
        self.load()
        with self.lock:
            self._merge(rows)

    def refresh(self):
        """Refresh name indexes off the primary search path, retaining stale data on failure."""
        import httpx
        if not self.directories:
            return
        directory = self.directories[0]
        directory.mkdir(parents=True, exist_ok=True)
        for filename in ('games_appid.json', 'software_appid.json'):
            target = directory/filename
            if target.exists() and time.time()-target.stat().st_mtime < 21600:
                continue
            try:
                url = 'https://raw.githubusercontent.com/jsnli/steamappidlist/master/data/' + filename
                response = httpx.get(url, timeout=8, follow_redirects=True)
                response.raise_for_status()
                if len(response.content) > 32*1024*1024:
                    raise ValueError('Catalog response too large')
                payload = response.json()
                rows = [{'app_id':k,'name':v} for k,v in payload.items()] if isinstance(payload,dict) else payload
                if not isinstance(rows,list) or not rows:
                    raise ValueError('Empty or invalid catalog response')
                self.merge(rows)
                fd, name = tempfile.mkstemp(prefix='.catalog-', dir=directory)
                try:
                    with os.fdopen(fd,'wb') as handle:
                        handle.write(response.content)
                    Path(name).replace(target)
                finally:
                    Path(name).unlink(missing_ok=True)
            except Exception:
                logger.debug('Catalog name refresh failed; retaining cached names', exc_info=True)

    def persist(self, rows):
        if not self.extra_file or not rows:
            return
        with self.lock:
            cached = {}
            if self.extra_file.is_file():
                try:
                    for row in json.loads(self.extra_file.read_text(encoding="utf-8")):
                        if isinstance(row,dict) and str(row.get('app_id','')).isdigit():
                            cached[int(row['app_id'])] = row
                except (OSError, ValueError, TypeError):
                    logger.debug('Replacing invalid supplemental cache',exc_info=True)
            for row in rows:
                if str(row.get('app_id','')).isdigit():
                    cached[int(row['app_id'])] = {**cached.get(int(row['app_id']), {}), **row}
            self.extra_file.parent.mkdir(parents=True,exist_ok=True)
            fd,name=tempfile.mkstemp(prefix='.catalog-extra-',dir=self.extra_file.parent)
            try:
                with os.fdopen(fd,'w', encoding='utf-8') as handle:
                    json.dump(list(cached.values())[-2000:],handle)
                Path(name).replace(self.extra_file)
            finally:
                Path(name).unlink(missing_ok=True)

    def search(self, query, offset, per_page, sort_by='updated', tag='', block_nsfw=False):
        from sff.gui.bridges.store_bridge import (_normalize_for_search, _alias_expanded_queries,
            _store_search_score, _looks_nsfw_by_name, _NONGAME_NAME_KW)
        self.load()
        offset = max(0, int(offset)); per_page = min(100, max(1, int(per_page)))
        query = str(query).strip()[:200]
        key = (query, sort_by, tag, bool(block_nsfw))
        with self.lock:
            matches = self.cache.get(key)
            if matches is None:
                variants = [_normalize_for_search(v).split() for v in (_alias_expanded_queries(query) or [query])]
                numeric = query.isascii() and query.isdigit()
                matches = []
                for aid, row in self.rows.items():
                    if not ((numeric and str(aid).startswith(query)) or any(ts and all(t in row['norm'] for t in ts) for ts in variants)):
                        continue
                    if row.get('type') in ('dlc', 'music', 'video', 'tool') or any(kw in row['name'].lower() for kw in _NONGAME_NAME_KW):
                        continue
                    if tag and str(tag).lower() not in [str(t).lower() for t in (row.get('tags') or [])]:
                        continue
                    if block_nsfw and (row.get('nsfw') or _looks_nsfw_by_name(row['name'])):
                        continue
                    if _store_search_score(query, row['name'], aid)[0] < 99:
                        matches.append(row)
                if sort_by in ('name_asc', 'name_desc'):
                    matches.sort(key=lambda r: r['name'].casefold(), reverse=sort_by == 'name_desc')
                elif sort_by in ('newest', 'oldest'):
                    matches.sort(key=lambda r: r['app_id'], reverse=sort_by == 'newest')
                matches.sort(key=lambda r: _store_search_score(query, r['name'], r['app_id'])[0])
                self.cache[key] = matches
                while len(self.cache) > 32:
                    self.cache.popitem(last=False)
            games = []
            for source in matches[offset:offset+per_page]:
                row = {k:v for k,v in source.items() if k != 'norm'}
                row.setdefault('image_url', row.get('header_image') or f"https://cdn.akamai.steamstatic.com/steam/apps/{row['app_id']}/header.jpg")
                games.append(row)
            return {'games': games, 'total': len(matches), 'has_fallback_data': bool(self.rows)}


def search(bridge, query, offset, per_page, sort_by, tag, request_id):
    from sff.game_list_fallback import _iter_store_metadata_dirs
    from sff.gui.bridges.store_bridge import _store_blocks_nsfw
    from ember.config import DATA
    index = getattr(bridge, '_ember_catalog', None)
    if index is None:
        index = bridge._ember_catalog = CatalogIndex(_iter_store_metadata_dirs(), DATA/'catalog-supplement.json')
    request = (str(query)[:200], max(0, offset), min(100, max(1, per_page)), sort_by, tag, str(request_id))
    bridge._ember_catalog_current = request
    if getattr(bridge, '_ember_catalog_local_busy', False):
        bridge._ember_catalog_local_pending = request
        return
    bridge._ember_catalog_local_busy = True
    block = _store_blocks_nsfw()
    started = time.monotonic()
    def local():
        return index.search(*request[:5], block_nsfw=block)
    def done(data):
        bridge._ember_catalog_local_busy = False
        if bridge._ember_catalog_current == request:
            bridge.search_results.emit(json.dumps(dict(data, request_id=request[5])))
            logger.info('Catalog local query %r: %.0f ms, %s matches', request[0], (time.monotonic()-started)*1000, data['total'])
            _queue_enrichment(bridge, index, request, block)
        pending = getattr(bridge, '_ember_catalog_local_pending', None)
        bridge._ember_catalog_local_pending = None
        if pending:
            search(bridge, *pending)
    def error(message):
        logger.warning('Local catalog failed: %s', message)
        done({'games': [], 'total': 0, 'error': str(message)})
    bridge._run_async(local, on_done=done, on_error=error)


def _queue_enrichment(bridge, index, request, block):
    if getattr(bridge, '_ember_catalog_remote_busy', False):
        bridge._ember_catalog_remote_pending = (request, block)
        return
    recent = getattr(bridge, '_ember_catalog_recent', {})
    bridge._ember_catalog_recent = recent
    key = request[:5] + (block,)
    if time.monotonic() - recent.get(key, -1000) < 300:
        return
    bridge._ember_catalog_remote_busy = True
    def work():
        from sff.gui.bridges.store_bridge import _alias_expanded_queries, _fetch_steam_image_urls
        if bridge._ember_catalog_current != request:
            return None
        rows = []
        try:
            client = bridge._get_store_client()
            if client:
                variants = _alias_expanded_queries(request[0]) or [request[0]]
                for query in variants[:2]:
                    if bridge._ember_catalog_current != request:
                        return None
                    for game in client.search_library(query, limit=100, search_by_appid=request[0].isdigit()) or []:
                        rows.append({'app_id': game.app_id, 'name': game.name, 'status': game.status or '', 'size': game.size or 0, 'source': 'hubcap'})
        except Exception:
            logger.debug('Catalog supplemental source unavailable; local results retained', exc_info=True)
        index.merge(rows)
        index.persist(rows)
        if bridge._ember_catalog_current != request:
            return None
        page = index.search(*request[:5], block_nsfw=block)
        try:
            images, types, adult = _fetch_steam_image_urls([r['app_id'] for r in page['games']])
            enriched = [dict(r, image_url=images.get(r['app_id']) or r.get('image_url'), nsfw=adult.get(r['app_id'],r.get('nsfw',False)), type='dlc' if types.get(r['app_id'])==2 else r.get('type','')) for r in page['games']]
            index.merge(enriched)
            index.persist(enriched)
        except Exception:
            logger.debug('Catalog artwork enrichment unavailable', exc_info=True)
        index.refresh()
        result = index.search(*request[:5], block_nsfw=block)
        result['has_hubcap'] = bool(client) if 'client' in locals() else False
        return result
    def done(data):
        bridge._ember_catalog_remote_busy = False
        if data and bridge._ember_catalog_current == request:
            recent[key] = time.monotonic()
            while len(recent)>64:
                recent.pop(next(iter(recent)))
            bridge.task_finished.emit(json.dumps({'task':'ember_search_enrichment','request_id':request[5],**data}))
        pending = getattr(bridge,'_ember_catalog_remote_pending',None)
        bridge._ember_catalog_remote_pending = None
        if pending and bridge._ember_catalog_current == pending[0]:
            _queue_enrichment(bridge,index,*pending)
    def error(message):
        logger.debug('Catalog enrichment failed: %s',message)
        done(None)
    bridge._run_async(work,on_done=done,on_error=error)
