"""Keep pytest out of this directory.

smoke_test.py and test_exports.py are command-line verification scripts — they
drive a real browser and read the generated workbook — but their names match
pytest's default discovery patterns (test_*.py and *_test.py). Bare `pytest`
therefore imported them and failed at collection on the stock CI image, which
installs only flake8 and pytest, long before any real test ran.

Renaming them would hide what they are. Ignoring them here fixes it for every
invocation, including `pytest mobile/`, rather than only for the bare run that
pytest.ini's testpaths covers.

Run them directly, with their dependencies installed:

    python3 mobile/tools/smoke_test.py
    python3 mobile/tools/test_exports.py
"""
collect_ignore_glob = ["*.py"]
