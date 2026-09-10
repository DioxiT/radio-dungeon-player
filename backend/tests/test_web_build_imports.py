"""The web build must import without yt-dlp installed.

CI for the static site installs only httpx, beautifulsoup4 and python-dotenv - it reads
the channel through its public preview and expands albums through bandcamp's own json,
so yt-dlp is never called. It was still being dragged in by an import chain
(sync_catalog -> web_sync -> sync_core -> resolver -> yt_dlp), which passed locally and
failed in CI. This test blocks yt_dlp outright and imports what the build imports.

    cd backend && .venv/bin/python tests/test_web_build_imports.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

DATA = Path(tempfile.mkdtemp(prefix="rdp-imports-"))
os.environ["TG_MODE"] = "anonymous"
os.environ["TG_DATA_DIR"] = str(DATA)


class BlockYtDlp:
    """Make yt_dlp look uninstalled, the way it is on the build runner."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "yt_dlp" or fullname.startswith("yt_dlp."):
            raise ModuleNotFoundError("No module named 'yt_dlp'")
        return None


for name in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
    del sys.modules[name]
sys.meta_path.insert(0, BlockYtDlp())

failures = []


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -> ' + detail}")
    if not condition:
        failures.append(label)


# The blocker itself has to work, otherwise this test proves nothing.
try:
    import yt_dlp  # noqa: F401

    check("yt_dlp действительно заблокирован", False, "импорт прошёл")
except ModuleNotFoundError:
    check("yt_dlp действительно заблокирован", True)

try:
    from app import bandcamp  # noqa: F401

    check("app.bandcamp импортируется", True)
except Exception as exc:
    check("app.bandcamp импортируется", False, f"{type(exc).__name__}: {exc}")

try:
    from app import sync_core  # noqa: F401

    check("app.sync_core импортируется", True)
except Exception as exc:
    check("app.sync_core импортируется", False, f"{type(exc).__name__}: {exc}")

try:
    from app import web_sync  # noqa: F401

    check("app.web_sync импортируется", True)
except Exception as exc:
    check("app.web_sync импортируется", False, f"{type(exc).__name__}: {exc}")

try:
    from tools import sync_catalog  # noqa: F401

    check("tools.sync_catalog импортируется", True)
except Exception as exc:
    check("tools.sync_catalog импортируется", False, f"{type(exc).__name__}: {exc}")

try:
    from tools import build_site_data  # noqa: F401

    check("tools.build_site_data импортируется", True)
except Exception as exc:
    check("tools.build_site_data импортируется", False, f"{type(exc).__name__}: {exc}")

# The desktop sync still needs yt-dlp - it just must not be needed to import the module.
check("sync_core не держит resolver на уровне модуля",
      not hasattr(sync_core, "resolver"),
      "resolver импортирован на уровне модуля")

shutil.rmtree(DATA, ignore_errors=True)
print("\nFailures:", len(failures) or "none")
raise SystemExit(1 if failures else 0)
