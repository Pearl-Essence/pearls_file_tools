"""CI-compatible GUI smoke test.

Drives every sidebar destination, opens every menu-bar dialog, exercises the
breadcrumb, save/load settings, repeated nav, and basic memory hygiene
(repeated MainWindow construction). Runs headless via QT_QPA_PLATFORM=offscreen.

Catches:
  - Import errors / missing modules
  - Constructor errors in any tab or dialog
  - Signal-connection breakage
  - Missing icons or QSS tokens
  - Settings persistence regressions
  - Repeated-tab-construction memory leaks (rough)

Exit code 0 if everything constructs and activates cleanly; 1 if any phase failed.

Run from repo root:
  QT_QPA_PLATFORM=offscreen python tests/gui_smoke_test.py
"""

from __future__ import annotations

import gc
import os
import sys
import time
import traceback
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)


# ─── helpers ────────────────────────────────────────────────────────────────

FAIL_COUNT = 0


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"=== {title}")
    print("=" * 70)


def passed(msg: str) -> None:
    print(f"  ✓ {msg}")


def failed(msg: str) -> None:
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"  ✗ {msg}")


def make_app_themed():
    from branding import APP_NAME
    from main import _apply_theme

    QApplication.instance().setApplicationName(APP_NAME)
    _apply_theme(QApplication.instance())


# ─── PHASE 1: Construct MainWindow + activate every nav key ────────────────


def phase_construct_and_navigate() -> None:
    banner("PHASE 1: MainWindow constructs and every sidebar key activates")
    from branding import NAV_TREE
    from ui.main_window import MainWindow

    make_app_themed()
    win = MainWindow()
    win.show()
    QApplication.processEvents()

    keys: List[str] = [k for _s, items in NAV_TREE for _l, _i, k in items]
    print(f"Found {len(keys)} sidebar destinations: {keys}")

    activated = 0
    for key in keys:
        try:
            win._on_nav_activated(key)
            QApplication.processEvents()
            activated += 1
        except Exception as e:
            failed(f"Activating {key!r}: {type(e).__name__}: {e}")
    if activated == len(keys):
        passed(f"All {activated} sidebar destinations activated")

    if hasattr(win, "_crumb") and win._crumb.text() and win._crumb.text() != "—":
        passed(f"Breadcrumb updated: {win._crumb.text()!r}")
    else:
        failed("Breadcrumb did not update during navigation")
    win.close()


# ─── PHASE 2: Every menu-bar dialog constructs ────────────────────────────


def phase_menu_dialogs() -> None:
    banner("PHASE 2: Menu-bar dialogs construct without errors")
    from config import Config
    from ui.dialogs.history_dialog import HistoryDialog
    from ui.dialogs.profile_dialog import ProfileDialog
    from ui.dialogs.settings_dialog import SettingsDialog

    cfg = Config()
    cfg.load_from_file()

    dialogs = [
        ("HistoryDialog", lambda: HistoryDialog()),
        ("SettingsDialog", lambda: SettingsDialog(cfg)),
        ("ProfileDialog", lambda: ProfileDialog(cfg)),
    ]
    for name, factory in dialogs:
        try:
            d = factory()
            d.show()
            QApplication.processEvents()
            d.close()
            passed(f"{name} constructed + shown + closed")
        except Exception as e:
            failed(f"{name}: {type(e).__name__}: {e}")
            traceback.print_exc()


# ─── PHASE 3: Settings round-trip via every tab's save/load ────────────────


def phase_settings_roundtrip() -> None:
    banner("PHASE 3: Each tab's save_settings + load_settings completes")
    from ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    QApplication.processEvents()

    save_failures = 0
    load_failures = 0
    for tab in win._tab_instances:
        name = tab.get_tab_name()
        try:
            tab.save_settings()
        except Exception as e:
            save_failures += 1
            failed(f"{name}.save_settings(): {type(e).__name__}: {e}")
        try:
            tab.load_settings()
        except Exception as e:
            load_failures += 1
            failed(f"{name}.load_settings(): {type(e).__name__}: {e}")

    if save_failures == 0 and load_failures == 0:
        passed(f"All {len(win._tab_instances)} tabs save+load settings cleanly")
    win.close()


# ─── PHASE 4: Repeated MainWindow construction (memory hygiene) ────────────


def phase_repeated_construction() -> None:
    banner("PHASE 4: Construct + tear down MainWindow 5x (memory hygiene)")
    from ui.main_window import MainWindow

    elapsed: List[float] = []
    for i in range(5):
        t0 = time.perf_counter()
        win = MainWindow()
        win.show()
        QApplication.processEvents()
        win.close()
        del win
        gc.collect()
        elapsed.append(time.perf_counter() - t0)

    avg = sum(elapsed) / len(elapsed)
    drift = elapsed[-1] - elapsed[0]
    passed(f"5 construction cycles: avg {avg*1000:.0f}ms, drift {drift*1000:+.0f}ms")
    if drift > 1.0:
        failed(f"Cycle time drifted by {drift:.2f}s — possible leak")


# ─── PHASE 5: Repeated tab activation ──────────────────────────────────────


def phase_rapid_navigation() -> None:
    banner("PHASE 5: Rapid round-robin navigation across all tabs (50 cycles)")
    from branding import NAV_TREE
    from ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    QApplication.processEvents()

    keys = [k for _s, items in NAV_TREE for _l, _i, k in items]
    iterations = 50
    crashes = 0
    t0 = time.perf_counter()
    for cycle in range(iterations):
        for key in keys:
            try:
                win._on_nav_activated(key)
            except Exception as e:
                crashes += 1
                if crashes <= 3:
                    failed(f"cycle {cycle} key {key!r}: {e}")
        QApplication.processEvents()
    elapsed = time.perf_counter() - t0
    total_acts = iterations * len(keys)
    if crashes == 0:
        passed(f"{total_acts} activations in {elapsed:.2f}s ({total_acts/elapsed:.0f}/s) — clean")
    else:
        failed(f"{crashes}/{total_acts} activations crashed")
    win.close()


# ─── PHASE 6: QSS theme loaded + serif resolved ───────────────────────────


def phase_theme_resolution() -> None:
    banner("PHASE 6: QSS load + brand serif resolution")
    from branding import QSS_PATH
    from main import _resolve_serif

    if QSS_PATH.exists():
        size = QSS_PATH.stat().st_size
        passed(f"QSS file present: {size} bytes")
    else:
        failed(f"QSS file missing: {QSS_PATH}")

    serif = _resolve_serif()
    if serif and serif != "serif":
        passed(f"Brand serif resolved to a real family: {serif!r}")
    else:
        failed(f"Brand serif fell through to generic: {serif!r}")

    qss_text = QSS_PATH.read_text() if QSS_PATH.exists() else ""
    if "__BRAND_SERIF__" in qss_text:
        passed("QSS still contains __BRAND_SERIF__ token")
    else:
        failed("QSS missing __BRAND_SERIF__ token — fonts won't apply")


# ─── PHASE 7: All placeholder SVGs present ─────────────────────────────────


def phase_svg_assets() -> None:
    banner("PHASE 7: All placeholder SVGs referenced by NAV_TREE exist")
    from branding import ICONS_DIR, NAV_TREE

    missing: List[str] = []
    for _section, items in NAV_TREE:
        for _label, icon_filename, _key in items:
            p = ICONS_DIR / icon_filename
            if not p.exists():
                missing.append(icon_filename)

    if not missing:
        present = sum(1 for f in ICONS_DIR.glob("*.svg"))
        passed(f"All NAV_TREE icons resolve. {present} SVGs in icons/")
    else:
        for m in missing:
            failed(f"Missing icon: {m}")


# ─── main ─────────────────────────────────────────────────────────────────


def main() -> int:
    phases = [
        phase_construct_and_navigate,
        phase_menu_dialogs,
        phase_settings_roundtrip,
        phase_repeated_construction,
        phase_rapid_navigation,
        phase_theme_resolution,
        phase_svg_assets,
    ]
    for fn in phases:
        try:
            fn()
        except Exception:
            print(f"\n!!! Unhandled exception in {fn.__name__}:")
            traceback.print_exc()
            global FAIL_COUNT
            FAIL_COUNT += 1

    print("\n" + "=" * 70)
    if FAIL_COUNT == 0:
        print("✓ ALL GUI SMOKE PHASES PASSED")
        return 0
    else:
        print(f"✗ {FAIL_COUNT} FAILURES — see above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
