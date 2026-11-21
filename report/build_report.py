"""Build the report as Word (.docx) and PDF from report.md.

    cd report
    python build_report.py

Needs: pandoc (with --citeproc), python-docx, and LibreOffice for the PDF.
Steps: pandoc turns the Markdown into a .docx, then python-docx sets the page,
font (Times New Roman, black), table borders and page numbers, and LibreOffice
exports the PDF.
"""
import shutil
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
SRC = HERE / "report.md"
RAW = HERE / "_raw.docx"
OUT = HERE / "report.docx"

FONT = "Times New Roman"
BLACK = RGBColor(0x00, 0x00, 0x00)


def run_pandoc():
    subprocess.run(["pandoc", str(SRC), "--resource-path", str(HERE),
                    "-o", str(RAW)], check=True, cwd=HERE)


def set_style(doc, name, size=None, bold=None, italic=None, color=None,
              before=None, after=None, align=None, keep_next=None, line=None):
    # match by name, ignoring case (pandoc writes "Heading 1", Word "heading 1")
    st = next((x for x in doc.styles
               if x.name and x.name.lower() == name.lower()), None)
    if st is None:
        print("style not found:", name)
        return
    f = st.font
    f.name = FONT
    rfonts = st.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        rfonts.attrib.pop(qn(f"w:{attr}"), None)
    if size: f.size = Pt(size)
    if bold is not None: f.bold = bold
    if italic is not None: f.italic = italic
    if color is not None:
        f.color.rgb = color
        col = st.element.rPr.find(qn("w:color"))
        for attr in ("themeColor", "themeShade", "themeTint"):
            col.attrib.pop(qn(f"w:{attr}"), None)
    pf = st.paragraph_format
    if before is not None: pf.space_before = Pt(before)
    if after is not None: pf.space_after = Pt(after)
    if align is not None: pf.alignment = align
    if keep_next is not None: pf.keep_with_next = keep_next
    if line is not None: pf.line_spacing = line


TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
               "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
               "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption",
               "tblDescription"]


def insert_ordered(parent, child, order):
    """Insert child into parent at the place the OOXML schema expects."""
    name = child.tag.split("}")[1]
    later = order[order.index(name) + 1:]
    for el in parent:
        if el.tag.split("}")[1] in later:
            el.addprevious(child)
            return
    parent.append(child)


def border(el_parent, tag, edges):
    """Add borders (dict edge -> size in eighths of a point) to tblPr."""
    b = OxmlElement(tag)
    for edge, sz in edges.items():
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single" if sz else "nil")
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "000000")
        b.append(e)
    insert_ordered(el_parent, b, TBLPR_ORDER)


def style_table(table, widths_cm, font_size=11, centre=False):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER if centre else WD_TABLE_ALIGNMENT.LEFT
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    border(tblPr, "w:tblBorders", {"top": 12, "left": 0, "bottom": 12, "right": 0,
                                   "insideH": 2, "insideV": 0})
    # fixed widths so Word and LibreOffice agree
    for old in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(old)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    insert_ordered(tblPr, layout, TBLPR_ORDER)
    for row_i, row in enumerate(table.rows):
        for j, cell in enumerate(row.cells):
            cell.width = Cm(widths_cm[j])
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                for r in p.runs:
                    r.font.size = Pt(font_size)
                    r.font.name = FONT
                    r.font.color.rgb = BLACK
                    if row_i == 0:
                        r.font.bold = True
    # keep each table on one page: rows cannot split and each row keeps
    # with the next one
    for row_i, row in enumerate(table.rows):
        trPr = row._tr.get_or_add_trPr()
        cs = OxmlElement("w:cantSplit")
        trPr.append(cs)
        if row_i < len(table.rows) - 1:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True
    grid = table._tbl.tblGrid
    for j, gc in enumerate(grid.findall(qn("w:gridCol"))):
        gc.set(qn("w:w"), str(int(widths_cm[j] * 567)))


def add_page_number_footer(section):
    section.different_first_page_header_footer = True
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            run._r.append(fc)
        else:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = text
            run._r.append(it)
    run.font.size = Pt(11)
    run.font.name = FONT
    run.font.color.rgb = BLACK


# ---------------------------------------------------------------- XML tidy-up
# pandoc 3.1 writes a few elements in an order that the strict OOXML schema
# does not allow. Word usually copes, but we put them in the right order so
# the file is fully valid.
ORDER = {
    "pPr": ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
            "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
            "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
            "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
            "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
            "suppressOverlap", "jc", "textDirection", "textAlignment",
            "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr",
            "pPrChange"],
    "rPr": ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps",
            "strike", "dstrike", "outline", "shadow", "emboss", "imprint", "noProof",
            "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
            "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd",
            "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
            "specVanish", "oMath"],
    "tcPr": ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
             "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark"],
    "tblPr": TBLPR_ORDER,
    "style": ["name", "aliases", "basedOn", "next", "link", "autoRedefine", "hidden",
              "uiPriority", "semiHidden", "unhideWhenUsed", "qFormat", "locked",
              "personal", "personalCompose", "personalReply", "rsid", "pPr", "rPr",
              "tblPr", "trPr", "tcPr", "tblStylePr"],
    "settings": ["writeProtection", "view", "zoom", "removePersonalInformation",
                 "embedTrueTypeFonts", "embedSystemFonts", "saveSubsetFonts",
                 "proofState", "stylePaneFormatFilter", "doNotTrackMoves",
                 "defaultTabStop", "drawingGridHorizontalSpacing",
                 "drawingGridVerticalSpacing", "displayHorizontalDrawingGridEvery",
                 "displayVerticalDrawingGridEvery", "characterSpacingControl",
                 "savePreviewPicture", "footnotePr", "endnotePr", "compat", "rsids", "mathPr",
                 "themeFontLang", "clrSchemeMapping", "decimalSymbol", "listSeparator"],
}


def _local(el):
    return el.tag.split("}")[1] if isinstance(el.tag, str) and "}" in el.tag else ""


def tidy(root):
    for el in root.iter():
        name = _local(el)
        if name in ORDER and len(el):
            order = ORDER[name]
            kids = list(el)
            # drop stray text inside element-only containers
            el.text = None
            for k in kids:
                k.tail = None
            known = sorted([k for k in kids if _local(k) in order],
                           key=lambda k: order.index(_local(k)))
            unknown = [k for k in kids if _local(k) not in order]
            for k in kids:
                el.remove(k)
            for k in known + unknown:
                el.append(k)
        if name == "nsid":                      # must be 8 hex digits
            v = el.get(qn("w:val"))
            if v and len(v) != 8:
                el.set(qn("w:val"), v[-8:].rjust(8, "0"))


def tidy_all(doc):
    tidy(doc.element)
    tidy(doc.styles.element)
    tidy(doc.settings.element)
    try:
        tidy(doc.part.numbering_part.element)
    except Exception:
        pass
    for s in doc.sections:
        s.header_distance, s.footer_distance, s.gutter = Cm(1.2), Cm(1.2), Cm(0)
        for part in (s.footer, s.first_page_footer, s.header, s.first_page_header):
            tidy(part._element)


def polish():
    doc = Document(str(RAW))

    # page: A4 with 2.3 cm margins
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21.0), Cm(29.7)
        s.left_margin = s.right_margin = Cm(2.3)
        s.top_margin = s.bottom_margin = Cm(2.2)
        add_page_number_footer(s)

    J = WD_ALIGN_PARAGRAPH.JUSTIFY
    C = WD_ALIGN_PARAGRAPH.CENTER
    body = dict(size=12, color=BLACK, after=6, line=1.15)
    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        set_style(doc, name, **body)
    set_style(doc, "Body Text", align=J)
    set_style(doc, "First Paragraph", align=J)
    set_style(doc, "Compact", after=3)
    set_style(doc, "Title", size=20, bold=True, color=BLACK, before=12, after=6,
              align=C)
    set_style(doc, "Subtitle", size=14, italic=False, bold=False, color=BLACK,
              after=36, align=C)
    set_style(doc, "Cover Text", size=12, color=BLACK, before=6, after=12, align=C)
    set_style(doc, "Heading 1", size=14, bold=True, color=BLACK, before=18, after=6,
              keep_next=True)
    set_style(doc, "Heading 2", size=12, bold=True, color=BLACK, before=12, after=4,
              keep_next=True)
    set_style(doc, "Heading 3", size=12, bold=True, italic=False, color=BLACK,
              before=12, after=4, keep_next=True)
    set_style(doc, "Image Caption", size=10, italic=True, color=BLACK, after=10,
              align=C)
    set_style(doc, "Table Caption", size=10, bold=False, italic=True, color=BLACK,
              before=6, after=4, keep_next=True, align=C)
    set_style(doc, "Captioned Figure", after=2, align=C, keep_next=True)

    # first cover line sits lower on the page
    for p in doc.paragraphs:
        if p.style.name.lower() == "cover text":
            p.paragraph_format.space_before = Pt(150)
            break

    # tables: 0 = cover members, 1 = columns, 2 = summary
    tables = doc.tables
    style_table(tables[0], [6.0, 4.0], centre=True)
    style_table(tables[1], [4.6, 11.8], centre=True)
    style_table(tables[2], [1.4, 11.0, 4.0], centre=True)

    # every run in black Times New Roman (pandoc may set its own colours)
    for p in doc.paragraphs:
        for r in p.runs:
            r.font.color.rgb = BLACK
            r.font.name = FONT

    tidy_all(doc)
    doc.save(str(OUT))
    RAW.unlink()


def export_pdf():
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("LibreOffice not found - skipped the PDF export.")
        return
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir",
                    str(HERE), str(OUT)], check=True, capture_output=True)


if __name__ == "__main__":
    run_pandoc()
    polish()
    export_pdf()
    print("Built", OUT.name, "and report.pdf")
