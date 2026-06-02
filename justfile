# women_editors — task runner
# Run `just` (or `just --list`) to see all recipes.

# Base throttle (seconds) between HTTP requests; override: `just delay=0.5 packs`
delay := "1"

# Output filename for the static report
report := "output/women_editors_report.html"

# Show available recipes
default:
    @just --list

# Download everything and rebuild all artifacts (packs, mislabels CSV, report)
rebuild: download-all mislabels report

# Install/refresh the virtual environment from the lockfile
sync:
    uv sync

# --- Download ---------------------------------------------------------------

# Phase 1: download the paginated pack index (resumable)
listing:
    uv run download.py listing --delay {{delay}}

# Phase 2: download details for woman-edited packs only (resumable)
packs:
    uv run download.py packs --delay {{delay}} --scope women

# Phase 2 (full): download details for EVERY pack (~6.7k, resumable)
packs-all:
    uv run download.py packs --delay {{delay}} --scope all

# Listing + woman-edited details, in order
download: listing packs

# Listing + ALL pack details, in order
download-all:
    uv run download.py all --delay {{delay}} --scope all

# --- Analyse ----------------------------------------------------------------

# Regenerate the output/mislabels_*.csv/.txt lists from the downloaded packs
mislabels:
    uv run detect_mislabels.py

# Open the analyser as an interactive marimo notebook
edit:
    uv run marimo edit analysis.py

# Serve the analyser as a read-only app
app:
    uv run marimo run analysis.py

# Export a static, non-interactive HTML report → output/women_editors_report.html
report:
    mkdir -p output
    uv run marimo export html analysis.py --no-include-code -o {{report}}

# Same, but with the Python source included
report-with-code:
    mkdir -p output
    uv run marimo export html analysis.py -o {{report}}

# Build a kernel-less interactive WASM notebook (Pyodide) with baked data,
# into output/wasm/ — serve as static files (e.g. GitHub Pages).
wasm: mislabels
    uv run marimo export html-wasm analysis.py -o output/wasm --mode run --no-show-code -f
    uv run bake_wasm.py

# Serve the built WASM notebook locally (must be over HTTP, not file://)
wasm-serve:
    python -m http.server --directory output/wasm 8000

# --- Housekeeping -----------------------------------------------------------

# How much has been downloaded so far
status:
    @echo "listing pages: $(ls data/listing/*.json 2>/dev/null | wc -l | tr -d ' ')"
    @echo "pack details:  $(ls data/packs/*.json 2>/dev/null | wc -l | tr -d ' ')"
    @du -sh data 2>/dev/null || true

# Delete downloaded pack details (keeps the listing index)
clean-packs:
    rm -f data/packs/*.json

# Delete all downloaded data
clean-data:
    rm -rf data

# Delete generated analysis artifacts (CSVs + report)
clean-output:
    rm -rf output
