# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Download one versioned source release, verify it and open its terminal installer."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

RELEASE = 'v0.2.0-preview'
BASE = 'https://github.com/Ch3L1k/Ember/releases/download/' + RELEASE


def verify(archive, checksums):
    matches = re.findall(r'^([0-9a-fA-F]{64})\s+\*?Ember-Source\.zip\s*$', checksums, re.M)
    if len(matches) != 1:
        raise ValueError('The release has no unique source archive checksum.')
    with archive.open('rb') as handle:
        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
    if actual != matches[0].lower():
        raise ValueError('Source archive checksum mismatch. Nothing was installed.')


def extract(archive, destination):
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 10000 or sum(e.file_size for e in entries) > 512 * 1024 * 1024:
            raise ValueError('Source archive exceeds extraction limits.')
        names = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'Ember'
                    or '\\' in entry.filename or ':' in entry.filename
                    or any(ord(c) < 32 for c in entry.filename)
                    or stat.S_ISLNK(entry.external_attr >> 16) or entry.filename in names):
                raise ValueError('Invalid archive entry.')
            names.add(entry.filename)
        if not {'Ember/install.sh', 'Ember/packaging/terminal_installer.py'} <= names:
            raise ValueError('Source archive does not include the terminal installer.')
        destination.mkdir(parents=True, exist_ok=True)
        package.extractall(destination)


def download(url, target, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'Ember-Installer'})
    with urllib.request.urlopen(request, timeout=60) as response, target.open('wb') as output:
        if not response.url.startswith('https://'):
            raise ValueError('Refusing a non-HTTPS download redirect.')
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError('Release download exceeds size limit.')
            output.write(chunk)


def main():
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise RuntimeError('Use Ember-Setup-windows.exe on Windows. This command is for Linux x86_64.')
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 or newer is required.')
    if os.geteuid() == 0:
        raise RuntimeError('Run without sudo, as your normal user.')
    print('\n  Ember · ' + RELEASE + '\n  Downloading the source package…', flush=True)
    with tempfile.TemporaryDirectory(prefix='ember-setup-') as directory:
        root = Path(directory)
        archive = root / 'Ember-Source.zip'
        checksum = root / 'SHA256SUMS.txt'
        download(BASE + '/SHA256SUMS.txt', checksum, 64 * 1024)
        download(BASE + '/Ember-Source.zip', archive, 256 * 1024 * 1024)
        verify(archive, checksum.read_text(encoding='utf-8-sig'))
        print('  SHA-256 verified. Opening installer.\n', flush=True)
        extract(archive, root / 'source')
        return subprocess.call(['bash', str(root / 'source/Ember/install.sh'), *sys.argv[1:]])


if __name__ == '__main__':
    try: raise SystemExit(main())
    except KeyboardInterrupt: raise SystemExit(130)
    except Exception as error:
        print('Ember installer: ' + str(error), file=sys.stderr)
        print('No working installation was replaced. Check the release download and try again.', file=sys.stderr)
        raise SystemExit(1)
