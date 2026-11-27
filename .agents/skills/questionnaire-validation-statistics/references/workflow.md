# CLI and report reference

## Runtime

- On macOS, the launcher can use `/Applications/jamovi.app`. Set `JAMOVI_APP` for another location. The launcher uses the bundled R runtime and bundles from the same app; it does not launch the GUI.
- On other systems (or to select a different runtime), install R and run `install.packages(c("jmv", "jsonlite"))` in R. For Excel also install `readxl`; for native jamovi files also install `jmvReadWrite`. Set `RSCRIPT` to force a particular `Rscript` executable. See the [jamovi `jmv` package](https://www.jamovi.org/jmv.html).
- The Word renderer requires Python 3 and `python-docx` (`python3 -m pip install python-docx`, preferably in an activated virtual environment).

```sh
bash "$skill/scripts/jamovi-cli" --version
bash "$skill/scripts/jamovi-cli" study.csv analysis-plan.json --figures figures > results.json
# On Windows without Bash, use this equivalent invocation in PowerShell:
# Rscript --vanilla "$skill/scripts/analyze.R" study.csv analysis-plan.json --figures figures > results.json
python3 "$skill/scripts/report.py" report-content.json report.docx
```

In the commands, `$skill` is the absolute path to the directory with `SKILL.md`. Run in a fresh output directory so shell redirection cannot replace a prior `results.json`. `--figures` is optional, and its argument must be a new directory. The Word renderer refuses to overwrite an existing file. The skill computes locally, but reading data into an agent conversation is subject to the host's configured provider and data handling.

## Analysis plan and data

CSV input requires UTF-8, comma delimiters, and a header row. XLSX uses the first sheet or an explicit top-level `"sheet": "Responses"`. Native `.omv` import applies saved active filters and configured missing values; describe these in the report and check the resulting row count against the original study file. Choose types from the codebook instead of guessing from storage types. Declare numeric missing sentinels as text, e.g. `"99"`. Leading zeros in IDs must be present as text in the source.

```json
{
  "columns": {
    "group": {"type": "nominal", "levels": ["Control", "Program"]},
    "item_a": {"type": "continuous", "range": [1, 5], "missing": ["99"]},
    "item_b": {"type": "continuous", "range": [1, 5], "missing": ["99"]}
  },
  "scores": [
    {"name": "scale_mean", "items": ["item_a", "item_b"], "reverse": ["item_b"],
     "range": [1, 5], "method": "mean", "min_answered": 2}
  ],
  "analyses": [
    {"id": "pilot-reliability", "method": "reliability",
     "options": {"vars": ["item_a", "item_b"], "revItems": ["item_b"], "itemRestCor": true}},
    {"id": "RQ1-descriptives", "method": "descriptives",
     "options": {"vars": ["scale_mean"], "splitBy": ["group"], "n": true, "missing": true,
                 "hist": true}},
    {"id": "RQ2-group-comparison", "method": "ttestIS",
     "options": {"vars": ["scale_mean"], "group": "group", "students": false,
                 "welchs": true, "desc": true, "meanDiff": true, "ci": true, "effectSize": true}}
  ]
}
```

- Required: `columns` maps original column names to types. Types are `continuous`, `nominal`, `ordinal`, and `text`. Set `levels` in the intended order for ordinal values and for nominal groups where order matters. Only `continuous` columns accept numeric `range` bounds. Treat numerical Likert item codes as `continuous` only where the scoring or selected method requires the numerical representation; document that use.
- Omit `scores`, `analyses`, and `cvi` for an audit. Results include counts of valid, missing, and invalid entries for each declared column. Invalid entries block requested computations; resolve the values and rerun. Undeclared columns are unavailable to jamovi. A score is derived in memory; mean scoring may allow partial item response under a documented rule, and sum scoring requires all items. Reversal is `minimum + maximum - response`. For reliability use the original item names and select `revItems` separately; the runner uses complete cases across those items.
- Supported `jmv` methods: `descriptives`, `reliability`, `ttestOneS`, `ttestIS`, `ttestPS`, `anovaOneW`, `anovaNP`, `anovaRM`, `anovaRMNP`, `ancova`, `mancova`, `corrMatrix`, `contTables`, `contTablesPaired`, `propTest2`, `propTestN`, `linReg`, `logRegBin`, `logRegMulti`, `logRegOrd`, `pca`, `efa`, and `cfa`. Look up exact options in the [`jmv` reference manual](https://cran.r-project.org/web/packages/jmv/refman/jmv.html). For a paired t-test, use `"options": {"pairs": [{"i1": "pre", "i2": "post"}], "desc": true, "meanDiff": true, "ci": true, "effectSize": true}`. Match each row to one observation unit (e.g. one respondent, with time points in separate columns for paired tests). `data` and `formula` are not accepted analysis options; use the structured variable fields.
- The JSON contains visible jamovi result tables. When `--figures` is used, each successful analysis also contains a `figures` array with paths within the jamovi result tree and, for each PNG saved, its `file` name relative to the export directory. A failed plot has `status: "error"` and a reason instead of a file. Figures are saved only for visible plot results, so select the relevant jamovi plot options in the analysis plan.
- `status: "error"` and `status: "blocked"` are recorded per analysis and for CVI; structured output can be valid even when an analysis failed. A `null` value is unavailable, not zero. The runner does not select models, tests, contrast direction, missingness rules, or suitable thresholds on the user's behalf.

### Plotting ordered responses

For a single Likert item, declare it as `ordinal` with the actual response codes in order, such as `"levels": ["1", "2", "3", "4"]`, and use `descriptives` with `"options": {"vars": ["Q1"], "freq": true, "bar": true, "barCounts": true}` to export both counts and a count plot. Compare the plot with the frequency table; the plot may omit levels with zero responses. Include the response anchors, any unused levels, the valid denominator and any missing responses in the report. If the objective also explicitly requires arithmetic on the same codes, use a separate numeric analysis plan so the measurement choice is documented and the distribution stays categorical. For continuous outcomes or aggregate scales, choose plots appropriate to the distribution or comparison, and state what any error bars show.

### CVI using a separate expert ratings file

Use a file with one row per expert and a separate ID column. Declare the rating items as numeric columns and supply the actual integer rating scale. For example:

```json
{
  "columns": {
    "expert_id": {"type": "text"},
    "Q1": {"type": "continuous", "range": [1, 4]},
    "Q2": {"type": "continuous", "range": [1, 4]}
  },
  "cvi": {"expert_id": "expert_id", "items": ["Q1", "Q2"],
          "range": [1, 4], "relevant_at_least": 3}
}
```

The skill computes these indices by explicit counts alongside jamovi results. I-CVI is the proportion of valid ratings at or above the relevance threshold, requiring at least two ratings on the item. With complete panel ratings, S-CVI/Ave is the mean of the item indices and S-CVI/UA is the proportion of items that all experts rated relevant. With any incomplete panel coverage, both scale indices are left unavailable and item-level missingness is reported. Keep these results separate from participant responses and from reliability.

## Report content

```json
{
  "kind": "questionnaire",
  "subject": "Synthetic instrument: Workshop Feedback Survey",
  "scope": ["The blank questionnaire was reviewed before pilot testing."],
  "findings": [{
    "caption": "Recommended item revision",
    "columns": ["Item", "Finding", "Recommended revision"],
    "rows": [["Q1", "The item combines clarity and pace.", "Use a separate item for each construct."]]
  }],
  "recommendation": ["Pilot the revised form before drawing conclusions about reliability."]
}
```

For a statistical report, use `kind: "statistics"` and replace `findings` with `objectives`. For example, with the exported plot from a synthetic Likert item:

```json
{
  "kind": "statistics",
  "subject": "Synthetic Workshop Feedback Survey",
  "scope": ["Three (3) valid responses to Q1 were analyzed."],
  "objectives": [{
    "title": "RQ1. Describe responses to the clarity item",
    "tables": [{
      "caption": "Response distribution for Q1",
      "columns": ["Response", "Count"],
      "rows": [["Strongly disagree", "0"], ["Disagree", "1"], ["Agree", "2"], ["Strongly agree", "0"]],
      "notes": ["Denominator: 3 valid responses. Missing: 0."]
    }],
    "figures": [{
      "file": "figures/analysis-1-figure-1.png",
      "caption": "Counts for Q1. Codes 1–4 correspond to the order shown in Table I.",
      "alt_text": "One response was recorded for disagree and two for agree."
    }],
    "interpretation": [
      "As shown in Table I and Fig. 1, two (2) of the three (3) respondents agreed with the clarity statement. This result describes the supplied responses."
    ]
  }],
  "recommendation": ["Report the denominator alongside the distribution."]
}
```

- Tables accept two to six columns, at least one body row, an optional `caption`, and optional `notes` (an array of strings). All table cells are strings. `summary_tables` and `follow_up_tables` use the same format. Older statistical JSON with `findings` still renders.
- For figures, take the actual filename from a successful jamovi result. Provide the PNG path relative to the report JSON directory, plus a caption and descriptive alt text. Do not add numbering to captions yourself: the renderer numbers tables (`Table I.`, `Table II.`) in document order, including summary tables, and figures (`Fig. 1.`, `Fig. 2.`) separately. Each objective displays its tables, figures, and then its interpretation.
- Use readable tables rather than copying all raw jamovi output. Preserve verified results through the prose edit, keep identifiers out of the report, and retain draft status until human review.
