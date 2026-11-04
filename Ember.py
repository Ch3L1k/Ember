# Ember — Copyright (C) 2026 Ember contributors.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details (LICENSE).

import logging
import faulthandler
import os
import sys

from ember.config import DATA

os.environ["EMBER_DATA_DIR"] = str(DATA)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", handlers=[logging.FileHandler(DATA / "ember.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)])
faulthandler.enable()

if __name__ == "__main__":
    from ember.core import main
    raise SystemExit(main())
