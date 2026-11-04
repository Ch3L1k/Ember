# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export reviewed source files; never package the working directory wholesale."""
import argparse
import hashlib
import importlib.metadata
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS = {'.py', '.lua', '.js', '.cjs', '.css', '.html', '.svg', '.png', '.ico', '.jpg', '.qrc', '.yaml', '.json', '.txt', '.md', '.nsi', '.ps1', '.spec', '.yml', '.toml', '.sh'}
TREES = ('ember', 'lab', 'sff', 'packaging', 'third_party_licenses', '.github', 'docs/assets')
FILES = ('Ember.py', 'EmberRuntime.py', 'Main.py', 'Main_gui.py', 'LICENSE', 'EMBER-NOTICES.txt',
         'install.sh', 'install-online.sh', 'README.md', 'README-linux.md', 'README-EMBER.txt', 'CHANGELOG.md', 'requirements.txt', 'requirements-linux.txt', 'requirements-build.txt',
         'THIRD-PARTY.txt', 'build_ember.spec', '.gitignore', '.gitattributes', 'docs/UPSTREAM-README.md', 'docs/README.ru.md', 'docs/INSTALL.md')
DENY = {'__pycache__', 'fallback_depotkeys.json', 'fallback_tokens.json', 'trionine_depotkeys.json', 'contributor_state.json', '.DS_Store'}


def dependency_notices():
    folder = ROOT / 'third_party_licenses/python'
    folder.mkdir(parents=True, exist_ok=True)
    lines = ['Ember bundled Python dependencies', '', 'Python 3.11: Python Software Foundation License.',
             'PyQt6: GPL v3 (this distribution uses the GPL option). Qt: see Qt license files.', '']
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
        name = dist.metadata['Name']
        license_name = (dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See package license files').strip()
        lines.append(f'{name} {dist.version} — {license_name[:400]}')
        for file in dist.files or []:
            path = Path(str(file))
            if path.is_absolute() or '..' in path.parts:
                continue
            if re.match(r'(?i)^(license|licence|copying|notice|authors)([._-].*)?$', path.name) and path.suffix.lower() not in {'.py', '.pyc', '.pyd'}:
                source = Path(dist.locate_file(file))
                if source.is_file() and source.stat().st_size < 2_000_000:
                    target = folder / name / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, folder / 'Python-LICENSE.txt')
    (ROOT / 'THIRD-PARTY.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def selected():
    for name in FILES:
        source = ROOT / name
        if source.is_file():
            yield source
    for directory in TREES:
        for source in sorted((ROOT / directory).rglob('*')):
            if not source.is_file() or source.is_symlink() or any(part in DENY for part in source.parts):
                continue
            if source.suffix.lower() in EXTENSIONS or directory == 'third_party_licenses':
                yield source


def export(target):
    target = Path(target).resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError('Use an empty destination for the source export')
    target.mkdir(parents=True, exist_ok=True)
    manifest = {}
    required = {'EmberRuntime.py', 'ember/millennium/backend.lua', 'ember/millennium/frontend.js',
                'ember/millennium/webkit.js', 'ember/web/Ember.ico', 'sff/webui/index.html',
                'packaging/installer.nsi', 'build_ember.spec', 'requirements.txt', 'LICENSE'}
    secrets = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|AKIA[0-9A-Z]{16})')
    for source in selected():
        relative = source.relative_to(ROOT)
        content = source.read_bytes()
        if source.suffix.lower() == ".sh":
            content = content.replace(b"\r\n", b"\n")
        if secrets.search(content):
            raise ValueError('Potential credential in ' + str(relative))
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        manifest[relative.as_posix()] = hashlib.sha256(content).hexdigest()
    if required - manifest.keys():
        raise ValueError('Required source files were not exported: ' + ', '.join(sorted(required - manifest.keys())))
    (target / 'SOURCE-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    archive = target.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for source in sorted(target.rglob('*')):
            if source.is_file():
                output.write(source, 'Ember/' + source.relative_to(target).as_posix())
    print(json.dumps({'source': str(target), 'archive': str(archive), 'files': len(manifest)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--notices', action='store_true')
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    if args.notices:
        dependency_notices()
    if args.export:
        export(args.export)
