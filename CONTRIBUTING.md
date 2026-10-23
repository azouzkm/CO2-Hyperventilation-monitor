# Working on this repository

Six of us share this repository. A few habits keep it tidy and protect the marks.

## Ground rules

1. **Never commit straight to `main`.** Work on a branch and open a pull request, so someone else
   sees the change before it is merged.
2. **No patient information, ever.** Bench data only: no names, phone numbers or photos of people
   in data, documents or commit messages.
3. **No secrets.** Messaging API keys and Wi-Fi passwords live in a local `.env` file (or the
   board's `settings.toml`); git ignores both.
4. **No videos or Excel files in git.** Videos go in the submission ZIP; save data as CSV.
5. **Name the requirement.** Say which CR, ER or deliverable a change serves, in the pull request
   and, where it fits, in the commit message (for example `D6: add the ER-2 protocol at 20 breaths/min`).
6. **Report what the bench shows.** When a requirement fails, record the evidence and the cause;
   never reword the requirement to fit the result.

## Where things go

| I have… | It goes in… |
| --- | --- |
| A deliverable write-up (D1–D8) | `docs/`, one file per deliverable, for example `docs/D2-system-design.md` |
| Text or tables for the final PDF | `docs/D9-dossier/` |
| A diagram (D4) | `docs/diagrams/`, with the source file (such as `.drawio`) next to the exported `.png` |
| A chart | `docs/figures/`, named `YYYY-MM-DD_what-it-shows.png` |
| A photo of the build | `docs/photos/` as `.jpg` (export iPhone `.HEIC` photos as JPEG first) |
| Bench readings or test results | `data/`, named `YYYY-MM-DD_what.csv` (see [data/README.md](data/README.md)) |
| Calibration data | `data/calibration/` |
| Notes from a bench session | A dated entry at the top of [docs/lab-notebook.md](docs/lab-notebook.md) |
| Code for the board | `firmware/` |
| Code for the laptop | `service/`, `dashboard/` or `tools/` |

Abdelaziz (GitHub: azouzkm) looks after `firmware/`, `tools/`, `tests/` and `hardware/`. For
changes there, open a pull request and ask him to review it.

## Editing on github.com (nothing to install)

Best for documents and small fixes.

1. Open the file on GitHub and click the pencil icon (**Edit this file**).
2. Make the change and check it in the **Preview** tab.
3. Click **Commit changes…**, write one line saying what changed and why, choose
   **Create a new branch for this commit and start a pull request**, then click **Propose changes**.
4. Click **Create pull request**.

To add files, open the folder and use **Add file → Upload files**; the same branch option is at
the bottom of the page.

## Working from a laptop

The first time, copy the repository and start a branch named for the work:

```bash
git clone https://github.com/azouzkm/CO2-Hypoventilation-Monitor.git
cd CO2-Hypoventilation-Monitor
git switch -c docs/d2-system-design
```

Make your changes, then save them to GitHub. Check the list that `git status` prints before
committing: no stray or secret files.

```bash
git add -A
git status
git commit -m "D2: first draft of the sensing approach"
git push -u origin docs/d2-system-design
```

GitHub then offers a **Compare & pull request** button. Before starting new work, bring your copy
up to date with `git switch main` and then `git pull`.

Branch names start with what they hold: `docs/…` for write-ups, `fw/…` for firmware, `data/…` for
results, `fix/…` for corrections.

## Before you push code

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest tests/
```

The first line is only needed once.

GitHub runs the same tests on every pull request. A red ✗ next to the pull request means something
broke; click it to see which test failed.
