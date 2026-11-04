# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = 'https://downloads.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip'
SHA256 = 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'

if __name__ == '__main__':
    destination = Path(sys.argv[1]).resolve()
    with urllib.request.urlopen(URL, timeout=90) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError('NSIS archive checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for entry in archive.infolist():
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Invalid archive path')
        archive.extractall(destination)
