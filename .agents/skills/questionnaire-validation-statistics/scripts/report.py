"""Render a review-ready Word draft using the supplied report layout."""

import argparse
import json
import sys
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.shared import Inches

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "report-template.docx"
CREDIT = "Engr. Jamie Eduardo Rosal, MSCpE"
ROLE = "Statistician and Questionnaire Validator"
LAYOUTS = {
    "questionnaire": (
        "Evaluation and Validation Report", "Scope and Overall Evaluation",
        "Recommended Questionnaire Revisions", "Validation Requirements and Recommendation",
    ),
    "statistics": (
        "Statistical Report", "Scope and Analysis Plan",
        "Statistical Results by Research Objective", "Interpretation and Recommendation",
    ),
}


def lines(value, label):
    if not isinstance(value, list) or not value or any(
        not isinstance(line, str) or not line.strip() for line in value
    ):
        raise ValueError(f"{label} must contain one or more nonempty strings")
    return value


def validate(spec):
    required = {"kind", "subject", "scope", "findings", "recommendation"}
    allowed = required | {"summary_tables", "follow_up_tables"}
    if not isinstance(spec, dict) or required - spec.keys() or spec.keys() - allowed:
        raise ValueError("Expected kind, subject, scope, findings, and recommendation")
    if not isinstance(spec["kind"], str) or spec["kind"] not in LAYOUTS:
        raise ValueError("kind must be 'questionnaire' or 'statistics'")
    lines([spec["subject"]], "subject")
    for field in ("scope", "recommendation"):
        lines(spec[field], field)
    for field in ("summary_tables", "findings", "follow_up_tables"):
        tables = spec.get(field, [])
        if not isinstance(tables, list) or (field == "findings" and not tables):
            raise ValueError(f"{field} must be a list of tables; findings must not be empty")
        for table in tables:
            if not isinstance(table, dict) or not {"columns", "rows"} <= table.keys() <= {
                "caption", "columns", "rows"
            }:
                raise ValueError("Each table needs columns and rows, with an optional caption")
            headers = lines(table["columns"], "columns")
            if not 2 <= len(headers) <= 6:
                raise ValueError("Use two to six columns per table")
            if "caption" in table:
                lines([table["caption"]], "caption")
            if not isinstance(table["rows"], list) or not table["rows"]:
                raise ValueError("Each table needs at least one row")
            for row in table["rows"]:
                if not isinstance(row, list) or len(row) != len(headers) or not all(
                    isinstance(cell, str) for cell in row
                ):
                    raise ValueError("Each row must have one text cell per column")


def add_table(document, table):
    if "caption" in table:
        document.add_paragraph(table["caption"], style="Caption")
    headers = table["columns"]
    result = document.add_table(rows=0, cols=len(headers), style="Table Grid")
    result.alignment = WD_TABLE_ALIGNMENT.CENTER
    result.autofit = False
    widths = {
        2: (1.62, 4.88),
        3: (1.30, 1.92, 3.28),
        4: (2.50, 1.30, 1.65, 1.05),
    }.get(len(headers), (6.5 / len(headers),) * len(headers))
    for column, width in zip(result.columns, widths):
        column.width = Inches(width)
    for index, row in enumerate([headers, *table["rows"]]):
        record = result.add_row()
        if index == 0:
            record._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
        for cell, value, width in zip(record.cells, row, widths):
            cell.width = Inches(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.style = "Report Table Text"
            paragraph.add_run(value).bold = index == 0


def generate(spec):
    validate(spec)
    document = Document(TEMPLATE)
    title, scope, findings, recommendation = LAYOUTS[spec["kind"]]
    formats = {paragraph.text: paragraph for paragraph in document.paragraphs}
    document._body.clear_content()

    def paragraph(value, role="Body"):
        template = formats[role]
        block = document.add_paragraph(style=template.style)
        if template._p.pPr is not None:
            block._p.replace(block._p.pPr, deepcopy(template._p.pPr))
        run = block.add_run(value)
        if template.runs[0]._r.rPr is not None:
            run._r.insert(0, deepcopy(template.runs[0]._r.rPr))
        return block

    def tables(field):
        for table in spec.get(field, []):
            add_table(document, table)

    paragraph(title, "Title")
    paragraph(spec["subject"], "Subtitle")
    paragraph(scope, "Heading")
    paragraph("Draft for review.")
    for value in spec["scope"]:
        paragraph(value)
    tables("summary_tables")
    paragraph(findings, "Heading")
    tables("findings")
    paragraph(recommendation, "Heading")
    tables("follow_up_tables")
    for value in spec["recommendation"]:
        paragraph(value)
    block = paragraph(f"Prepared by {CREDIT}", "Credit")
    block.add_run(f"\n{ROLE}")

    document.core_properties.title = title
    document.core_properties.subject = spec["subject"]
    document.core_properties.author = CREDIT
    document.core_properties.last_modified_by = ""
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if args.report.suffix.lower() != ".docx":
        parser.error("output path must end in .docx")
    try:
        spec = json.loads(args.content.read_text(encoding="utf-8"))
        output = BytesIO()
        generate(spec).save(output)
        with args.report.open("xb") as stream:
            stream.write(output.getbuffer())
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
