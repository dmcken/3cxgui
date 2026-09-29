# 3cxgui

A 3CX Web GUI automation library.

## Install

```bash
pip install -U git+https://github.com/dmcken/3cxgui.git
or
python3 -m pip install -U git+https://github.com/dmcken/3cxgui.git
```

This tracks the default branch, which moves as new commits land - fine
for local testing, but Docker builds and other downstream consumers
should pin to a released tag instead so builds don't silently change
underneath them:

```bash
pip install git+https://github.com/dmcken/3cxgui.git@v0.1.0
```

Available tags: https://github.com/dmcken/3cxgui/tags

## Notes:
* import is called cxgui (Python import rules).