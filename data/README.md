# The licensed match data goes here — and it is never committed.

This directory is ignored by git (see `.gitignore` at the repository root): the
More Than A Hack 2027 competition data is licensed to the teams that download it and may
not be redistributed. The only file tracked here is this README.

## What the pipeline expects

```
data/
├── tactical/
│   ├── BAR-ATH_tactical_atd.txt           raw tracking, one line per video frame
│   ├── BAR-ATH_tactical_atd.xml           teams and track slots
│   ├── BAR-ATH_tactical_homography.csv     per-frame homography
│   └── BAR-ATH_tactical_smart_tagging.xml  set-piece windows
└── broadcast/
    ├── BAR-ATH_broadcast_atd.txt
    ├── BAR-ATH_broadcast_atd.xml
    └── BAR-ATH_broadcast_homography.csv
```

The pipeline resolves the directory in this order: `--data-dir`, then the `MTAH_DATA_DIR`
environment variable, then this one.

## Verifying your copy

The repository ships `MANIFEST.sha256` at its root, with paths relative to this directory.
Unpack the bundle here and check it:

```bash
cd data
shasum -a 256 -c ../MANIFEST.sha256
```

Every file must report `OK`. A `FAILED` line means the copy is not the data the pipeline
was run against, and the results are not reproducible.
