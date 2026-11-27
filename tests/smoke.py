"""Exercise the public commands with synthetic inputs and independent answers."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents/skills/questionnaire-validation-statistics"
SCRIPTS = SKILL / "scripts"


def run(*args):
    process = subprocess.run(args, text=True, capture_output=True, check=False)
    assert process.returncode == 0, process.stderr
    return process.stdout


with TemporaryDirectory() as work:
    work = Path(work)
    csv = work / "pilot data.csv"
    csv.write_text(
        "expert,A,B,arm\n001,1,4,Control\n002,2,3,Control\n"
        "003,3,2,Program\n004,4,1,Program\n005,,2,Program\n",
        encoding="utf-8",
    )
    spec = work / "plan.json"
    config = {
        "columns": {
            "expert": {"type": "text"},
            "A": {"type": "continuous", "range": [1, 4]},
            "B": {"type": "continuous", "range": [1, 4]},
            "arm": {"type": "nominal", "levels": ["Control", "Program"]},
        },
        "scores": [{"name": "Scale", "items": ["A", "B"], "reverse": ["B"],
                    "range": [1, 4], "method": "mean", "min_answered": 2}],
        "analyses": [
            {"id": "RQ1", "method": "descriptives",
             "options": {"vars": ["Scale", "arm"], "freq": True}},
            {"id": "pilot", "method": "reliability",
             "options": {"vars": ["A", "B"], "revItems": ["B"], "itemRestCor": True}},
            {"id": "paired", "method": "ttestPS",
             "options": {"pairs": [{"i1": "A", "i2": "B"}], "meanDiff": True}},
            {"id": "groups", "method": "ttestIS",
             "options": {"vars": ["A"], "group": "arm", "students": False, "welchs": True}},
        ],
        "cvi": {"expert_id": "expert", "items": ["A", "B"],
                "range": [1, 4], "relevant_at_least": 3},
    }
    def analyze(data, plan):
        spec.write_text(json.dumps(plan), encoding="utf-8")
        return json.loads(run("bash", SCRIPTS / "jamovi-cli", data, spec))

    result = analyze(csv, config)
    assert result["engine"]["jmv"]
    assert result["profile"]["Scale"]["missing"] == 1
    assert all(item["status"] == "ok" for item in result["analyses"]), result["analyses"]
    desc, reliability, paired, groups = result["analyses"]
    values = desc["tables"][0]["rows"][0]
    assert values["Scale[n]"] == 4 and values["Scale[mean]"] == 2.5
    assert any(table["rows"][0].get("counts") == 2 for table in desc["tables"][1:])
    assert reliability["complete_cases"] == 4
    assert abs(reliability["tables"][0]["rows"][0]["alpha"] - 1) < 1e-10
    pair_values = paired["tables"][0]["rows"][0]
    assert pair_values["df[stud]"] == 3 and pair_values["md[stud]"] == 0
    assert groups["tables"][0]["notes"]["hyp"]
    assert result["cvi"]["items"]["A"]["rated"] == 4
    assert result["cvi"]["items"]["A"]["i_cvi"] == 0.5
    assert result["cvi"]["s_cvi_ave"] is None
    assert result["cvi"]["s_cvi_ua"] is None

    figure_dir = work / "jamovi figures"
    config["analyses"][0]["options"]["bar"] = True
    config["analyses"][0]["options"]["barCounts"] = True
    spec.write_text(json.dumps(config), encoding="utf-8")
    with_plots = json.loads(run("bash", SCRIPTS / "jamovi-cli", csv, spec, "--figures", figure_dir))
    assert with_plots["analyses"][0]["tables"] == desc["tables"]
    figures = with_plots["analyses"][0]["figures"]
    arm_plot = next(plot for plot in figures if plot["path"][-2:] == ['"arm"', "bar"])
    assert arm_plot["status"] == "ok", arm_plot
    image = figure_dir / arm_plot["file"]
    assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    complete = work / "complete.csv"
    complete.write_text("expert,A,B,arm\n001,3,4,Control\n002,4,2,Program\n", encoding="utf-8")
    result = analyze(complete, {"columns": config["columns"], "cvi": config["cvi"]})
    assert result["cvi"]["s_cvi_ave"] == 0.75
    assert result["cvi"]["s_cvi_ua"] == 0.5

    invalid = work / "invalid.csv"
    invalid.write_text(csv.read_text().replace("001,1", "001,9"), encoding="utf-8")
    result = analyze(invalid, config)
    assert result["profile"]["A"]["invalid"] == 1
    assert result["analyses"][0]["status"] == "blocked" and result["cvi"]["status"] == "blocked"

    ragged = work / "ragged.csv"
    ragged.write_text("A,B\n1,2,3\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", SCRIPTS / "jamovi-cli", ragged, spec], text=True, capture_output=True, check=False
    )
    assert result.returncode != 0 and "same number of fields" in result.stderr

    for kind, heading in (
        ("questionnaire", "Recommended Questionnaire Revisions"),
        ("statistics", "Statistical Results by Research Objective"),
    ):
        content = work / f"{kind}.json"
        content.write_text(json.dumps({
            "kind": kind, "subject": "Synthetic study", "scope": ["Only the supplied evidence."],
            "findings": [{"columns": ["Item", "Finding", "Recommended revision"],
                          "rows": [["Q1", "Two ideas in one item", "Split the item"]]}],
            "recommendation": ["Review draft before sign-off."],
        }), encoding="utf-8")
        report = work / f"{kind}.docx"
        run(sys.executable, SCRIPTS / "report.py", content, report)
        doc = Document(report)
        text = "\n".join(p.text for p in doc.paragraphs)
        assert heading in text and "Engr. Jamie Eduardo Rosal, MSCpE" in text
        assert "Statistician and Questionnaire Validator" in text
        assert doc.tables[0].cell(1, 0).text == "Q1"
        assert doc.sections[0].page_width.inches == 8.5
        with ZipFile(report) as parts:
            assert b"NUMPAGES" in parts.read("word/footer1.xml")
            assert all(
                not any(marker in parts.read(name) for marker in (b"ClinIQ", b"Group 5", b"Microsoft Office User"))
                for name in parts.namelist() if name.endswith(".xml")
            )
        repeated = subprocess.run(
            [sys.executable, SCRIPTS / "report.py", content, report], capture_output=True, check=False
        )
        assert repeated.returncode != 0

    illustrated = {
        "kind": "statistics", "subject": "Synthetic study",
        "scope": ["Only the supplied evidence."],
        "summary_tables": [{"caption": "Records reviewed", "columns": ["Type", "Count"],
                            "rows": [["Total", "5"]]}],
        "objectives": [{
            "title": "RQ1. Describe the study arms",
            "tables": [{"caption": "Responses by arm", "columns": ["Arm", "Count"],
                        "rows": [["Control", "2"], ["Program", "3"]],
                        "notes": ["Counts are based on five nonmissing arm assignments."]}],
            "figures": [{"file": image.relative_to(work).as_posix(), "caption": "Responses by arm",
                         "alt_text": "Two control and three program assignments."}],
            "interpretation": ["Table II and Fig. 1 show that three of the five records were from the program arm."],
        }],
        "recommendation": ["Review draft before sign-off."],
    }
    content = work / "illustrated.json"
    content.write_text(json.dumps(illustrated), encoding="utf-8")
    report = work / "illustrated.docx"
    run(sys.executable, SCRIPTS / "report.py", content, report)
    doc = Document(report)
    paragraphs = [p.text for p in doc.paragraphs]
    assert len(doc.inline_shapes) == 1 and doc.tables[1].cell(2, 1).text == "3"
    assert "Table I. Records reviewed" in paragraphs and "Table II. Responses by arm" in paragraphs
    assert "Counts are based on five nonmissing arm assignments." in paragraphs
    assert paragraphs.index("Fig. 1. Responses by arm") < paragraphs.index(
        illustrated["objectives"][0]["interpretation"][0]
    )
    assert doc.inline_shapes[0]._inline.docPr.get("descr") == "Two control and three program assignments."
    illustrated["objectives"][0]["figures"][0]["file"] = str(image)
    content.write_text(json.dumps(illustrated), encoding="utf-8")
    unsafe_output = work / "rejected.docx"
    failed = subprocess.run(
        [sys.executable, SCRIPTS / "report.py", content, unsafe_output], check=False, capture_output=True
    )
    assert failed.returncode != 0 and not unsafe_output.exists()

print("Synthetic jamovi, CVI, figures, and Word smoke checks passed.")
