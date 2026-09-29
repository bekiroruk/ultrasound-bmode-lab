# Offline evidence demo

Open `index.html` locally in a browser. All 8 scientific figures are embedded; no server, download or raw dataset is required. This is a precomputed evidence viewer, not real-time reconstruction.

Rebuild: `python scripts/build_portfolio.py` after the coverage, eCDF, measured transfer, sequence and native-profile commands. `manifest.json` hashes the embedded evidence inputs and generated HTML; JSON/HTML hashes use LF-normalized bytes for cross-platform consistency. Verify the saved package with `python scripts/build_portfolio.py --verify`. Supporting Markdown links work inside the repository checkout.
