"""Constructor puro en Python de ecuaciones Word OMML nativas escaladas a 8.5 pt.

No requiere Pandoc ni LaTeX instalados en el equipo de ejecución.
"""

from typing import Dict
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS_DECL = f'xmlns:m="{M_NS}" xmlns:w="{W_NS}"'

# Plantillas OMML compatibles con Microsoft Word (validadas con Pandoc/OOXML)
OMML_TEMPLATES: Dict[str, str] = {
    "rational": (
        f'<m:oMathPara {NS_DECL}><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        '<m:oMath>'
        '<m:sSub><m:e><m:r><m:t>Q</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>racional</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t> = </m:t></m:r>'
        '<m:r><m:t>0.00278</m:t></m:r>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>·</m:t></m:r><m:r><m:t>C</m:t></m:r>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>·</m:t></m:r><m:r><m:t>I</m:t></m:r>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>·</m:t></m:r><m:r><m:t>A</m:t></m:r>'
        '</m:oMath></m:oMathPara>'
    ),
    "inflow": (
        f'<m:oMathPara {NS_DECL}><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        '<m:oMath>'
        '<m:sSub><m:e><m:r><m:t>Q</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>entrada</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>(t) = </m:t></m:r>'
        '<m:sSub><m:e><m:r><m:t>f</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>ing</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>·</m:t></m:r>'
        '<m:sSub><m:e><m:r><m:t>Q</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>racional</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>(t) + </m:t></m:r>'
        '<m:sSub><m:e><m:r><m:t>Q</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>san</m:t></m:r></m:sub></m:sSub>'
        '</m:oMath></m:oMathPara>'
    ),
    "manning": (
        f'<m:oMathPara {NS_DECL}><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        '<m:oMath>'
        '<m:sSub><m:e><m:r><m:t>Q</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>max,</m:t></m:r><m:r><m:t>i</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t> = </m:t></m:r>'
        '<m:f><m:fPr><m:type m:val="bar"/></m:fPr><m:num><m:r><m:t>1</m:t></m:r></m:num>'
        '<m:den><m:sSub><m:e><m:r><m:t>n</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:den></m:f>'
        '<m:sSub><m:e><m:r><m:t>A</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub>'
        '<m:sSubSup><m:e><m:r><m:t>R</m:t></m:r></m:e>'
        '<m:sub><m:r><m:t>h</m:t></m:r><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>,</m:t></m:r><m:r><m:t>i</m:t></m:r></m:sub>'
        '<m:sup><m:r><m:t>2/3</m:t></m:r></m:sup></m:sSubSup>'
        '<m:sSubSup><m:e><m:r><m:t>S</m:t></m:r></m:e>'
        '<m:sub><m:r><m:t>i</m:t></m:r></m:sub>'
        '<m:sup><m:r><m:t>1/2</m:t></m:r></m:sup></m:sSubSup>'
        '</m:oMath></m:oMathPara>'
    ),
    "velocity": (
        f'<m:oMathPara {NS_DECL}><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        '<m:oMath>'
        '<m:sSub><m:e><m:r><m:t>V</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t> = </m:t></m:r>'
        '<m:f><m:fPr><m:type m:val="bar"/></m:fPr>'
        '<m:num><m:sSub><m:e><m:r><m:t>Q</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>max,</m:t></m:r><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:num>'
        '<m:den><m:sSub><m:e><m:r><m:t>A</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:den></m:f>'
        '</m:oMath></m:oMathPara>'
    ),
    "transit": (
        f'<m:oMathPara {NS_DECL}><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        '<m:oMath>'
        '<m:sSub><m:e><m:r><m:t>t</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t> = </m:t></m:r>'
        '<m:f><m:fPr><m:type m:val="bar"/></m:fPr>'
        '<m:num><m:sSub><m:e><m:r><m:t>L</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:num>'
        '<m:den><m:sSub><m:e><m:r><m:t>V</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:den></m:f>'
        '</m:oMath></m:oMathPara>'
    ),
    "utilization": (
        f'<m:oMathPara {NS_DECL}><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        '<m:oMath>'
        '<m:sSub><m:e><m:r><m:t>O</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>(t) = </m:t></m:r>'
        '<m:f><m:fPr><m:type m:val="bar"/></m:fPr>'
        '<m:num><m:sSub><m:e><m:r><m:t>Q</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>(t)</m:t></m:r></m:num>'
        '<m:den><m:sSub><m:e><m:r><m:t>Q</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>max,</m:t></m:r><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:den></m:f>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t> × </m:t></m:r><m:r><m:t>100</m:t></m:r>'
        '</m:oMath></m:oMathPara>'
    ),
    "mass_balance": (
        f'<m:oMathPara {NS_DECL}><m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        '<m:oMath>'
        '<m:sSub><m:e><m:r><m:t>V</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>iny</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>(t) = </m:t></m:r>'
        '<m:sSub><m:e><m:r><m:t>V</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>PTAR</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>(t) + </m:t></m:r>'
        '<m:sSub><m:e><m:r><m:t>V</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>pozos</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>(t) + </m:t></m:r>'
        '<m:sSub><m:e><m:r><m:t>V</m:t></m:r></m:e>'
        '<m:sub><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>tránsito</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>(t)</m:t></m:r>'
        '</m:oMath></m:oMathPara>'
    ),
}


def _apply_font_size_to_omml(omath_para: etree._Element, size_pt: float = 8.5) -> None:
    """Escala todos los runs matemáticos de OMML a `size_pt` (17 half-points = 8.5 pt)."""
    half_pts = str(int(round(size_pt * 2)))
    w_rpr_tag = f"{{{W_NS}}}rPr"
    w_sz_tag = f"{{{W_NS}}}sz"
    w_szcs_tag = f"{{{W_NS}}}szCs"
    w_fonts_tag = f"{{{W_NS}}}rFonts"

    for math_run in omath_para.findall(f".//{{{M_NS}}}r"):
        w_rpr = math_run.find(w_rpr_tag)
        if w_rpr is None:
            w_rpr = etree.Element(w_rpr_tag)
            # Insertar antes de m:t (o después de m:rPr si existe)
            m_rpr = math_run.find(f"{{{M_NS}}}rPr")
            idx = 1 if m_rpr is not None else 0
            math_run.insert(idx, w_rpr)

        fonts = w_rpr.find(w_fonts_tag)
        if fonts is None:
            fonts = etree.SubElement(w_rpr, w_fonts_tag)
        fonts.set(f"{{{W_NS}}}ascii", "Cambria Math")
        fonts.set(f"{{{W_NS}}}hAnsi", "Cambria Math")

        sz = w_rpr.find(w_sz_tag)
        if sz is None:
            sz = etree.SubElement(w_rpr, w_sz_tag)
        sz.set(f"{{{W_NS}}}val", half_pts)

        szcs = w_rpr.find(w_szcs_tag)
        if szcs is None:
            szcs = etree.SubElement(w_rpr, w_szcs_tag)
        szcs.set(f"{{{W_NS}}}val", half_pts)


def add_omml_equation(doc, template_key: str, eq_number: str = "", size_pt: float = 8.5) -> Paragraph:
    """Agrega una ecuación OMML independiente, centrada y escalada a `size_pt` (8.5 pt)."""
    if template_key not in OMML_TEMPLATES:
        raise KeyError(f"Ecuación OMML desconocida: {template_key}")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(3)

    omath_para = etree.fromstring(OMML_TEMPLATES[template_key])
    _apply_font_size_to_omml(omath_para, size_pt=size_pt)
    p._p.append(omath_para)

    if eq_number:
        run = p.add_run(f"   ({eq_number})")
        run.font.size = Pt(size_pt)
    return p
