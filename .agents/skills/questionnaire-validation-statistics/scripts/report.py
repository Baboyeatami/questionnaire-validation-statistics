"""Render a review-ready Word draft using the supplied report layout."""

import argparse
import json
import sys
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.image.exceptions import (
    InvalidImageStreamError,
    UnexpectedEndOfFileError,
    UnrecognizedImageError,
)
from docx.image.image import Image
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


def validate_tables(tables, field, required=False):
    if not isinstance(tables, list) or (required and not tables):
        raise ValueError(f"{field} must be a list of tables" + (" and cannot be empty" if required else ""))
    for table in tables:
        if not isinstance(table, dict) or not {"columns", "rows"} <= table.keys() <= {
            "caption", "columns", "rows", "notes"
        }:
            raise ValueError("Each table needs columns and rows, with an optional caption and notes")
        headers = table["columns"]
        lines(headers, "columns")
        if not 2 <= len(headers) <= 6:
            raise ValueError("Use two to six columns per table")
        if "caption" in table:
            lines([table["caption"]], "caption")
        if "notes" in table:
            lines(table["notes"], "notes")
        if not isinstance(table["rows"], list) or not table["rows"]:
            raise ValueError("Each table needs at least one row")
        for row in table["rows"]:
            if not isinstance(row, list) or len(row) != len(headers) or not all(
                isinstance(cell, str) for cell in row
            ):
                raise ValueError("Each row must have one text cell per column")


def validate(spec):
    required = {"kind", "subject", "scope", "recommendation"}
    allowed = required | {"summary_tables", "follow_up_tables", "findings", "objectives"}
    if not isinstance(spec, dict) or not required <= spec.keys() <= allowed:
        raise ValueError("Expected kind, subject, scope, recommendation, and findings or objectives")
    if not isinstance(spec["kind"], str) or spec["kind"] not in LAYOUTS:
        raise ValueError("kind must be 'questionnaire' or 'statistics'")
    lines([spec["subject"]], "subject")
    for field in ("scope", "recommendation"):
        lines(spec[field], field)
    for field in ("summary_tables", "follow_up_tables"):
        validate_tables(spec.get(field, []), field)
    if "objectives" not in spec:
        validate_tables(spec.get("findings", []), "findings", required=True)
        return
    if spec["kind"] != "statistics" or "findings" in spec:
        raise ValueError("Use objectives in statistical reports instead of findings")
    if not isinstance(spec["objectives"], list) or not spec["objectives"]:
        raise ValueError("objectives must be a nonempty list")
    for objective in spec["objectives"]:
        if not isinstance(objective, dict) or not {
            "title", "tables", "interpretation"
        } <= objective.keys() <= {"title", "tables", "figures", "interpretation"}:
            raise ValueError("Each objective needs a title, tables, and interpretation")
        lines([objective["title"]], "objective title")
        lines(objective["interpretation"], "interpretation")
        validate_tables(objective["tables"], "objective tables", required=True)
        figures = objective.get("figures", [])
        if not isinstance(figures, list):
            raise TypeError("figures must be a list")
        for figure in figures:
            if not isinstance(figure, dict) or figure.keys() != {"file", "caption", "alt_text"}:
                raise ValueError("Each figure needs a file, caption, and alt_text")
            for key in figure:
                lines([figure[key]], f"figure {key}")


def roman(number):
    result = []
    for value, symbol in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
                          (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                          (5, "V"), (4, "IV"), (1, "I")):
        copies, number = divmod(number, value)
        result.append(symbol * copies)
    return "".join(result)


def add_table(document, table, number):
    caption = document.add_paragraph(f"Table {roman(number)}. {table.get('caption', 'Results')}", style="Caption")
    caption.paragraph_format.keep_with_next = True
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
    for note in table.get("notes", []):
        document.add_paragraph(note, style="Report Table Text")


def add_figure(document, figure, number, content_dir):
    relative = Path(figure["file"])
    source = (content_dir / relative).resolve()
    if relative.is_absolute() or content_dir not in source.parents or source.suffix.lower() != ".png":
        raise ValueError("Figure file must be a relative PNG path below the report-content directory")
    try:
        image = Image.from_file(str(source))
        if image.content_type != "image/png" or not image.width or not image.height:
            raise ValueError(f"Expected a valid PNG figure: {relative}")
        width = min(Inches(6.5), Inches(5.5) * image.width / image.height)
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.keep_with_next = True
        shape = paragraph.add_run().add_picture(BytesIO(image.blob), width=int(width))
        shape._inline.docPr.set("descr", figure["alt_text"])
    except (InvalidImageStreamError, UnexpectedEndOfFileError, UnrecognizedImageError, ZeroDivisionError):
        raise ValueError(f"Expected a valid PNG figure: {relative}") from None
    caption = document.add_paragraph(f"Fig. {number}. {figure['caption']}", style="Caption")
    caption.paragraph_format.keep_with_next = False


def generate(spec, content_dir):
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

    table_number, figure_number = 0, 0

    def tables(items):
        nonlocal table_number
        for table in items:
            table_number += 1
            add_table(document, table, table_number)

    paragraph(title, "Title")
    paragraph(spec["subject"], "Subtitle")
    paragraph(scope, "Heading")
    paragraph("Draft for review.")
    for value in spec["scope"]:
        paragraph(value)
    tables(spec.get("summary_tables", []))
    paragraph(findings, "Heading")
    tables(spec.get("findings", []))
    for objective in spec.get("objectives", []):
        document.add_paragraph(objective["title"], style="Heading 2")
        tables(objective["tables"])
        for figure in objective.get("figures", []):
            figure_number += 1
            add_figure(document, figure, figure_number, content_dir)
        for value in objective["interpretation"]:
            paragraph(value)
    paragraph(recommendation, "Heading")
    tables(spec.get("follow_up_tables", []))
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
        generate(spec, args.content.resolve().parent).save(output)
        with args.report.open("xb") as stream:
            stream.write(output.getbuffer())
    except (ValueError, TypeError, OSError, KeyError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
