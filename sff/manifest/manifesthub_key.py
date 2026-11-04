# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

"""ManifestHub API key cache with auto-renewal (24 h validity)."""

import logging
import threading
import time
import webbrowser

from sff.ui.prompts import prompt_text

logger = logging.getLogger(__name__)

_KEY_URL = "https://manifesthub2.filegear-sg.me"
_EXPIRY_SECONDS = 86_400  # 24 h
_renewal_lock = threading.Lock()
_skipped_this_session = False


def _key_is_valid():
    from sff.core.storage.settings import get_setting
    from sff.core.structs import Settings

    key = get_setting(Settings.MANIFESTHUB_API_KEY)
    expiry_str = get_setting(Settings.MANIFESTHUB_KEY_EXPIRY)
    if not key or not expiry_str:
        return False
    try:
        return time.time() < float(expiry_str)
    except (ValueError, TypeError):
        return False


def _save_key(key):
    from sff.core.storage.settings import set_setting
    from sff.core.structs import Settings

    global _skipped_this_session
    _skipped_this_session = False
    set_setting(Settings.MANIFESTHUB_API_KEY, key)
    set_setting(Settings.MANIFESTHUB_KEY_EXPIRY, str(time.time() + _EXPIRY_SECONDS))


def get_manifesthub_api_key():
    """Get a valid key; opens the generator page in the user's browser if renewal needed."""
    global _skipped_this_session
    from sff.core.storage.settings import get_setting
    from sff.core.structs import Settings

    if _key_is_valid():
        return get_setting(Settings.MANIFESTHUB_API_KEY)
    # ManifestHub is the first source tried, so a blank answer must stick for
    # the whole run or every depot would re-prompt.
    if _skipped_this_session:
        return None

    with _renewal_lock:
        # Re-check inside lock — another parallel thread may have already renewed.
        if _key_is_valid():
            return get_setting(Settings.MANIFESTHUB_API_KEY)
        had_key = get_setting(Settings.MANIFESTHUB_API_KEY) is not None
        if had_key:
            print(f"ManifestHub API key expired. Opening renewal page: {_KEY_URL}")
        else:
            print(f"ManifestHub API key needed. Opening key generator: {_KEY_URL}")
        # Opens URL in the user's default/active browser — one tab, no flicker.
        webbrowser.open(_KEY_URL)
        pasted = prompt_text(
            "This download needs a manifest file. ManifestHub is a free service "
            "that provides them.\n\n"
            f"Your browser should have opened: {_KEY_URL}\n"
            "Copy the API key shown on that page, then paste it here.\n"
            "The key works for 24 hours, then this box appears again.\n\n"
            "No key? Leave the box empty and press OK. The download continues "
            "with the free mirror sources instead, which can be slower or miss "
            "the newest updates."
        ).strip()
        if pasted:
            _save_key(pasted)
            return pasted
        _skipped_this_session = True
        return None
