# More Than A Hack 2027 — frame-level ball possession.
#
# The pipeline is deterministic and CPU-only: `make reproduce` regenerates
# artifacts/submission.csv from the licensed match data, and `make validate`
# re-runs the official submission checks on the result.
#
# The match data is licensed and is not in this repository. See MANIFEST.sha256
# for the checksums a reviewer uses to verify their own download.

PYTHON     ?= python3
SUBMISSION ?= artifacts/submission.csv
REPORT     ?= artifacts/run_report.json
# 199,319 frames: the tactical video at 25 fps, and the row count of the submission.
FRAMES     ?= 199319

# The package lives in src/ and is not installed in the developer's environment.
export PYTHONPATH := src

.PHONY: all install install-dev reproduce validate test report clean help ask coverage ledger \
        external stability dead-onset demo

all: test validate

help:
	@echo "install      pip install -e ."
	@echo "install-dev  pip install -e '.[dev]' (adds pytest)"
	@echo "reproduce    run the pipeline, write $(SUBMISSION) and $(REPORT)"
	@echo "validate     check $(SUBMISSION) against the official rules"
	@echo "test         run the test suite (pytest -q)"
	@echo "report       print the summary of $(REPORT)"
	@echo "clean        remove the generated artefacts and the caches"
	@echo "ask          plumb ask '<question>' -- the interface the project is judged on"
	@echo "coverage     plumb coverage -- how much of the match the feed can carry"
	@echo "ledger       plumb ledger -- every claim, with its coverage"
	@echo "external     the external tuning sweep over Metrica's three sample matches"
	@echo "stability    the label-free merge-length criterion, on four matches"
	@echo "dead-onset   the three dead-ball onset rules, and what each costs"
	@echo "demo         the five-minute pitch, end to end, from the committed code"

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

reproduce:
	$(PYTHON) -m mtah.run --out artifacts/submission.csv --report artifacts/run_report.json

validate:
	@$(PYTHON) -c "import sys; from mtah.emit import validate_file; problems = validate_file('$(SUBMISSION)', $(FRAMES)); print('\n'.join(problems) if problems else 'OK: $(SUBMISSION) is a valid $(FRAMES)-row submission'); sys.exit(1 if problems else 0)"

test:
	$(PYTHON) -m pytest -q

report:
	@test -f $(REPORT) || { echo "no $(REPORT) yet; run 'make reproduce' first"; exit 1; }
	@$(PYTHON) -c "import json; r = json.load(open('$(REPORT)')); keys = ('frames', 'graded_frames', 'possessions', 'mean_possession_s', 'median_possession_s', 'max_possession_s', 'dead_spells', 'dead_seconds', 'home_share_of_alive', 'label_counts_graded', 'absence_classes'); print(json.dumps({k: r[k] for k in keys if k in r}, indent=2, sort_keys=True))"

# The interface: a question in, a supported answer or a refusal out.
ask:
	@$(PYTHON) -m plumb ask "$(Q)"

coverage:
	@$(PYTHON) -m plumb coverage

ledger:
	@$(PYTHON) -m plumb ledger

# The compliance evidence: every threshold is checked on data that is not the provided match.
external:
	$(PYTHON) scripts/external_tuning.py

stability:
	$(PYTHON) scripts/stability_sweep.py

dead-onset:
	$(PYTHON) scripts/dead_onset.py

# The pitch: five beats, deterministic, and it records the fallback transcript.
demo:
	$(PYTHON) scripts/demo.py --record docs/demo-transcript.txt

clean:
	rm -rf artifacts .pytest_cache
	rm -rf src/*.egg-info *.egg-info
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
