# Install and verify the application package

The installable Python package is now version **0.10.1**, with API **0.4.0**. The latest addition is the [native app solver comparison](32-native-solver-comparison.md), which tests training settings against the existing 11-category semantic model. Historical experiment commands remain available for reproduction, and browser prediction interfaces are unchanged. See [semantic browser setup](21-semantic-browser-mode.md).

The wheel includes Python modules, HTML/CSS/JavaScript, authored sample collections, aggregate experiment reports, and the dataset-license copy accompanying those reports. It does not include trained models, downloaded source data, private annotation files, or semantic encoder weights. Source-tree datasets and reports map into package resource directories during the build, so there are no duplicate source copies to maintain.

## Install from the repository

From the repository root in Python 3.11–3.13 (Python 3.12 is used for installed-package CI):

```bat
python -m pip install .
support-ticket-demo artifacts/demo-v1
support-ticket-serve --model-dir artifacts/demo-v1/model
```

Use a fresh output directory when building a new demo. Existing users with a working model can install the package and start `support-ticket-serve` against that existing trusted model without rebuilding it.

The demo builder downloads the pinned Bitext source and trains the existing word baseline. It does not install the experimental semantic model. Start the workspace at http://127.0.0.1:8000/. The server still binds to local loopback. Nothing is publicly hosted by installation.

Console commands:

| Command | Purpose |
|---|---|
| `support-ticket-ai PATH.csv` | Validate and summarize a demo-contract CSV |
| `support-ticket-demo OUTPUT_DIR` | Build a pinned-source demo bundle |
| `support-ticket-serve --model-dir MODEL_DIR` | Start the local workspace/API |
| `support-ticket-predict MODEL_DIR --text "..."` | Predict from a trusted local bundle |

The existing `python -m support_ticket_ai...` commands continue to work. Optional semantic experiments still require their separate requirements file; installing the core package does not download Torch or a sentence encoder. The package is built in this repository; no PyPI publication is implied.

## Build distribution files

Developer checks use an optional requirements file:

```bat
python -m pip install -r requirements-checks.txt
python -m build --outdir artifacts/dist
```

This creates a source distribution and a platform-independent Python wheel. The ML dependencies themselves use platform-specific wheels selected by pip. Build backend versions and direct application dependencies are pinned; transitive dependencies and downloaded platform wheels are not fully locked. This is a repeatable installation recipe, not a claim of byte-identical environments or wheel files across operating systems.

## Verify an installed wheel

`scripts/check_installed.py` refuses to run against an imported source checkout. Run it with the wheel installed in an environment outside the repository, and use an unrelated current directory. Its smoke checks create a tiny synthetic model fixture; they use no user labels, external dataset, final test set, or network model download.

Checks cover packaged sample/reference resources, web assets, readiness/liveness, valid/invalid predictions, optional abstention, and an absent-model 503 state while the UI remains accessible.

With `--browser`, Chromium additionally exercises desktop and mobile widths, real form submission through the local API, abstention, stale-result clearing, the character limit, network-error recovery, unavailable status, readiness retry, and JavaScript exceptions. Browser readiness/network failures are deliberately simulated to test frontend handling. The fixture API and model are real. Synthetic fixture correctness is a software smoke check, not ML quality evidence.

The **Installed package and browser checks** workflow builds and installs the wheel into a new environment, runs the check outside the checkout, and uploads the wheel, source distribution, browser trace, logs, and desktop/mobile screenshots for seven days. Existing Python checks remain in place for Python 3.11, 3.12, and 3.13. Installed-package/browser CI currently runs on Linux/Python 3.12; Windows installation and other browsers are not certified by that job.

## Packaging choices

Reference-file resolution prefers the installed resource directories and falls back to the existing source locations during development. Default experiment/review paths therefore survive installation. Private reviews under `artifacts/` remain excluded. Wheels contain aggregate development reports and unscored authored collections; their inclusion does not promote any model or establish additional accuracy.

A clean wheel installation is tested separately from source tests because passing tests inside a checkout can hide missing web assets or default data files. This milestone verifies delivery and interaction rather than collecting more annotation data.
