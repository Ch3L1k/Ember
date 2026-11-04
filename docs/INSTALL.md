# Installation

## Windows

Download `Ember-Setup.exe` from Releases. It installs for the current user into `%LOCALAPPDATA%\Programs\Ember`, with Start menu shortcuts and an uninstaller. The Python/Qt runtime is included. Close Ember before updating; close Steam if removing a Millennium adapter.

The installer is unsigned. Verify its SHA-256 against `SHA256SUMS.txt` from the same release. Do not disable antivirus protection to run a file you cannot verify.

Ember's UI integration works without Millennium. Game registration requires a compatible LumaCore installation; it is not included in this package. Availability and setup are documented by [SteaMidra](https://github.com/drappula/SFF).

Uninstall through Windows Settings. User settings, games and saves remain on disk.

## Linux

Requirements: Linux x86_64, native Steam, Python 3.11+ with `venv` and `ensurepip`, Git for a Python dependency, and internet access. On distributions which split Python into packages, install the `venv` package too. Qt system libraries must be available; the installer checks that the Python/Qt modules can load before activating the new version.

Extract `Ember-Source.zip`, enter `Ember`, then run:

```sh
bash install.sh
```

The menu offers install/update, dependency check and uninstall. The default destination is `~/.local/opt/ember`. It builds a new version before updating the launcher; a failed dependency installation leaves the old version selected. Previous version directories are retained until uninstall.

For scripted installation:

```sh
bash install.sh --action install --yes
bash install.sh --action check
```

Launch Ember from your application menu or `~/.local/bin/ember`. First launch configures the Steam UI integration. If Steam needs a restart, close it normally after finishing any running game.

Registration requires separately installed [SLSsteam](https://github.com/AceSLS/SLSsteam) and [lumalinux](https://github.com/jayool/lumalinux). A provider may also require an API key. The installer reports missing modules; it does not claim that installation of Ember alone enables every feature.

### Update

Close Ember with `ember --stop`, extract the new source package and run `bash install.sh`. Choose the same installation directory. The installer refuses to overwrite an unrelated or modified launcher.

For an older development checkout, first disable its integration with `ember --uninstall-integration`, then stop it. Keep that checkout as a backup and remove its old launcher/desktop entry only after checking their paths. The new installer deliberately does not take over unmanaged installations.

### Remove

From the source package:

```sh
ember --stop
bash install.sh --action uninstall
```

Alternatively run the installed copy:

```sh
python3 ~/.local/opt/ember/current/packaging/terminal_installer.py --action uninstall
```

Use `--prefix /your/path` for a non-default installation. Games, saves and `~/.local/share/ember/Desktop` remain. Separately installed game-registration modules are not removed.

## Data and logs

| Platform | Location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Ember\Desktop` |
| Linux | `$XDG_DATA_HOME/ember/Desktop`, default `~/.local/share/ember/Desktop` |

## Development

From the source root, create a virtual environment and install dependencies in two separate steps. The `steam` package has an outdated urllib3 constraint, so its installation uses `--no-deps`.

Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-linux.txt
.venv/bin/python -m pip install steam==1.4.4 --no-deps
.venv/bin/python EmberRuntime.py
```

Windows (PowerShell, Python 3.11 x64):

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pip install steam==1.4.4 --no-deps
.venv/Scripts/python.exe EmberRuntime.py
```

Build the Windows installer on Windows with NSIS:

```powershell
./packaging/build.ps1 -Output C:\Builds\Ember
```

Use a fresh output folder. This produces `Ember-Setup.exe`, `Ember-Source.zip` and `SHA256SUMS.txt`. The installer includes corresponding source and license notices.
