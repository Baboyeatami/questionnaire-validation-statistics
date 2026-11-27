# Questionnaire Validation and Statistical Reporting

One Agent Skill for **OpenCode** and **Codex**. It reviews research proposals and questionnaires, links objectives and items to dataset columns, runs jamovi analyses from the command line, and generates editable Word reports. It also computes content validity indices from expert ratings and checks the reliability of pilot scales when the available data support those analyses.

## Use

Clone this repository and open it as a workspace in either agent, or copy the entire `.agents/skills/questionnaire-validation-statistics` directory into the `.agents/skills/` directory of an existing study workspace. To make it available across your local projects, place the directory under `~/.agents/skills/` instead.

| Host | How to use it |
| --- | --- |
| OpenCode | Ask for `@questionnaire-validation-statistics` and name the input files. |
| Codex CLI or IDE | Select `$questionnaire-validation-statistics` and name the input files. |

Example:

> Use questionnaire-validation-statistics to review `Proposal.docx` and `Questionnaire.docx`, check `Pilot.csv` against `Codebook.xlsx`, and produce the Word reports supported by these files.

The same skill covers proposal-only or blank-questionnaire reviews, expert content-validity ratings, pilot response files, and full statistical analyses. Draft reports use the supplied layout and credit **Engr. Jamie Eduardo Rosal, MSCpE — Statistician and Questionnaire Validator**.

## Requirements

- Python 3 with `python-docx` for the Word reports.
- jamovi Desktop on macOS, or R with `jmv` and `jsonlite` for the data computations. The skill's `jamovi-cli` launcher runs jamovi's own `jmv` analysis package; it is not a command shipped with the desktop app. CSV is built in; Excel and native jamovi imports require `readxl` and `jmvReadWrite`, respectively.

See [the CLI and report reference](.agents/skills/questionnaire-validation-statistics/references/workflow.md) for analysis options, input formats, and example report content. Run `python3 tests/smoke.py` to check the command-line analysis, validation calculations, and Word exports using synthetic data.

The included Word template contains layout elements only. Keep actual proposals, questionnaires, study datasets, and generated reports in your study workspace.
