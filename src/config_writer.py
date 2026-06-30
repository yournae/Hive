"""Config writer for config.yaml — used by the interactive scheduler menu.

Prefers ruamel.yaml so the inline comments in config.yaml survive edits.
Falls back to PyYAML if ruamel isn't installed (comments will be lost, but the
menu won't crash). PyYAML is always available — it's used by src/config.py.

To keep comments on a worker, install ruamel:  venv/bin/pip install ruamel.yaml

Note: Config is loaded once at import time (src/config.py). Changes written
here take effect the next time the daemon process starts (systemd restart or
a fresh menu launch), not for an already-running scheduler.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

# ── Backend selection: ruamel (comment-preserving) → PyYAML (fallback) ──
_USE_RUAMEL = False
try:
    from ruamel.yaml import YAML
    _yaml = YAML()
    _yaml.preserve_quotes = True
    _yaml.indent(mapping=2, sequence=4, offset=2)
    _USE_RUAMEL = True
except ImportError:
    import yaml as _pyyaml


def comments_preserved():
    """True if edits keep config.yaml comments (ruamel available)."""
    return _USE_RUAMEL


def load():
    """Load config.yaml as a mutable mapping."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        if _USE_RUAMEL:
            return _yaml.load(f)
        return _pyyaml.safe_load(f) or {}


def save(data):
    """Write the mapping back to config.yaml atomically (temp file + rename)."""
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if _USE_RUAMEL:
            _yaml.dump(data, f)
        else:
            _pyyaml.safe_dump(data, f, allow_unicode=True,
                              sort_keys=False, default_flow_style=False)
    os.replace(tmp, CONFIG_PATH)


def _ensure(data, key):
    if key not in data or data[key] is None:
        data[key] = {}
    return data[key]


def _new_seq(items):
    """Build a sequence node appropriate for the active backend."""
    if _USE_RUAMEL:
        from ruamel.yaml.comments import CommentedSeq
        seq = CommentedSeq()
        for it in items:
            seq.append(it)
        return seq
    return list(items)


def set_mode(mode):
    """Set schedule.mode to 'fixed' or 'interval'."""
    assert mode in ("fixed", "interval")
    data = load()
    _ensure(data, "schedule")["mode"] = mode
    save(data)


def set_fixed_times(times):
    """Replace schedule.times with a list of 'HH:MM' strings."""
    data = load()
    _ensure(data, "schedule")["times"] = _new_seq(times)
    save(data)


def set_interval(interval_hours, start_hour):
    """Set schedule.interval_hours and schedule.start_hour."""
    data = load()
    sched = _ensure(data, "schedule")
    sched["interval_hours"] = int(interval_hours)
    sched["start_hour"] = int(start_hour)
    save(data)


def set_rest_hours(rest_start, rest_end):
    """Set schedule.rest_start and schedule.rest_end (hour 0-23)."""
    data = load()
    sched = _ensure(data, "schedule")
    sched["rest_start"] = int(rest_start)
    sched["rest_end"] = int(rest_end)
    save(data)


def set_timezone(tz_name):
    """Set schedule.timezone (IANA name like 'Asia/Jakarta')."""
    data = load()
    _ensure(data, "schedule")["timezone"] = str(tz_name)
    save(data)


def set_auto_generate(stock_min, batch_size):
    """Set auto_generate.stock_min and auto_generate.batch_size."""
    data = load()
    ag = _ensure(data, "auto_generate")
    ag["stock_min"] = int(stock_min)
    ag["batch_size"] = int(batch_size)
    save(data)
