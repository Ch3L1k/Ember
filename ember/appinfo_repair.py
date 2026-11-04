# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import hashlib
import logging
import os
import struct
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def patch_product_token(raw, app_id, token):
    app_id, token = int(app_id), int(token)
    if not 0 < app_id < 2**32 or not 0 < token < 2**64:
        raise ValueError('Invalid product-info identifier')
    if len(raw) < 12 or raw[:4] not in (b'(DV\x07', b')DV\x07'):
        raise ValueError('Unsupported Steam appinfo format')
    indexed = raw[:4] == b')DV\x07'
    if indexed and len(raw) < 20:
        raise ValueError('Truncated Steam appinfo header')
    limit = struct.unpack_from('<Q', raw, 8)[0] if indexed else len(raw)
    cursor = 16 if indexed else 8
    if not cursor + 4 <= limit <= len(raw):
        raise ValueError('Invalid Steam appinfo boundary')
    selected = None
    while cursor + 4 <= limit:
        current = struct.unpack_from('<I', raw, cursor)[0]
        if current == 0:
            if cursor + 4 != limit:
                raise ValueError('Unexpected Steam appinfo terminator')
            break
        if cursor + 8 > limit:
            raise ValueError('Truncated Steam appinfo entry')
        size = struct.unpack_from('<I', raw, cursor + 4)[0]
        if size < 60 or cursor + 8 + size > limit:
            raise ValueError('Invalid Steam appinfo entry size')
        if current == app_id:
            if selected is not None:
                raise ValueError('Duplicate Steam appinfo entry')
            selected = cursor + 16
        cursor += 8 + size
    else:
        raise ValueError('Missing Steam appinfo terminator')
    if selected is None:
        raise ValueError('Application is not present in the Steam appinfo cache')
    result = bytearray(raw)
    struct.pack_into('<Q', result, selected, token)
    return bytes(result)


def restore_product_token(steam, app_id, token, backup_dir):
    from ember.desktop import steam_processes
    from ember.host import steam_executable
    steam = Path(steam).resolve()
    target = steam / 'appcache/appinfo.vdf'
    if target.is_symlink() or target.resolve().parent != (steam / 'appcache').resolve():
        raise ValueError('Unexpected Steam appinfo location')
    if steam_processes(steam_executable(steam)):
        raise RuntimeError('Полностью закройте Steam перед восстановлением данных установки.')
    original = target.read_bytes()
    repaired = patch_product_token(original, app_id, token)
    if original == repaired:
        logger.info('Product-info token is already present for app %s', app_id)
        return {'changed': False}
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(original).hexdigest()
    backup = backup_dir / ('appinfo-' + digest + '.vdf')
    if not backup.exists():
        with backup.open('xb') as output:
            output.write(original)
    if backup.read_bytes() != original:
        raise RuntimeError('Appinfo backup verification failed')
    descriptor, temporary = tempfile.mkstemp(prefix='appinfo-repair-', suffix='.tmp', dir=target.parent)
    pending = Path(temporary)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(repaired)
            output.flush()
            os.fsync(output.fileno())
        if steam_processes(steam_executable(steam)) or target.read_bytes() != original:
            raise RuntimeError('Steam restarted or updated appinfo; repair was not applied')
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)
    logger.info('Restored product-info token for app %s; original appinfo backed up', app_id)
    return {'changed': True, 'backup': str(backup)}
