# certificates/pdf_export.py — PDF export for QuMail encryption certificates.
# Single responsibility: read a JSON certificate produced by cert_generator.py
# and render it as a formatted, human-readable PDF using fpdf2.
# Does not generate certificate data — cert_generator.py owns that.
# Do not import from transport/, ui/, portal/, kme/, or crypto/.

import json
import os

from fpdf import FPDF

from core.config import APP_NAME, APP_VERSION


# --- Layout Constants ---

_PAGE_MARGIN_MM      = 20      # Left/right page margin in millimetres
_PAGE_WIDTH_MM       = 210     # A4 width
_CONTENT_WIDTH_MM    = _PAGE_WIDTH_MM - (_PAGE_MARGIN_MM * 2)

_COLOUR_DEEP_BLUE    = (15,  55,  100)   # Header background / accent bar
_COLOUR_ACCENT_TEAL  = (0,   160, 160)   # Section divider line
_COLOUR_LABEL_GREY   = (100, 100, 100)   # Field label text
_COLOUR_VALUE_BLACK  = (20,  20,  20)    # Field value text
_COLOUR_WHITE        = (255, 255, 255)
_COLOUR_LIGHT_BG     = (245, 248, 252)   # Alternating row background

_FONT_FAMILY         = "Helvetica"       # Core 14 font — no embedding required

# Human-readable display labels for each JSON key, in display order.
_FIELD_ORDER: list[tuple[str, str]] = [
    ("cert_id",        "Certificate ID"),
    ("timestamp_utc",  "Issued At (UTC)"),
    ("tqr_level",      "TQR Security Level"),
    ("algorithm",      "Algorithm"),
    ("key_id",         "QKD Key UUID"),
    ("sender",         "Sender"),
    ("recipient_hash", "Recipient (SHA-256)"),
]


# --- Custom Exceptions ---

class PdfExportError(Exception):
    """Raised when reading the JSON cert or writing the PDF fails."""
    pass


# --- Internal Helpers ---

def _load_cert(json_path: str) -> dict:
    """
    Read and parse the JSON certificate file.

    Raises PdfExportError if the file cannot be opened or is not valid JSON.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise PdfExportError(
            f"Failed to read certificate file '{json_path}': {exc}"
        ) from exc


def _pdf_path_from_json(json_path: str) -> str:
    """
    Derive the output PDF path from the JSON cert path.

    Replaces the .json extension with .pdf in the same directory.
    """
    base, _ = os.path.splitext(json_path)
    return base + ".pdf"


def _draw_header(pdf: FPDF) -> None:
    """Render the branded header block at the top of the page."""
    # Deep blue background rectangle spanning the full content width.
    r, g, b = _COLOUR_DEEP_BLUE
    pdf.set_fill_color(r, g, b)
    pdf.rect(_PAGE_MARGIN_MM, 15, _CONTENT_WIDTH_MM, 28, style="F")

    # App name — large white bold text.
    r, g, b = _COLOUR_WHITE
    pdf.set_text_color(r, g, b)
    pdf.set_font(_FONT_FAMILY, style="B", size=20)
    pdf.set_xy(_PAGE_MARGIN_MM + 4, 18)
    pdf.cell(_CONTENT_WIDTH_MM - 8, 10, APP_NAME, align="L")

    # Subtitle — smaller white regular text.
    pdf.set_font(_FONT_FAMILY, size=9)
    pdf.set_xy(_PAGE_MARGIN_MM + 4, 28)
    pdf.cell(_CONTENT_WIDTH_MM - 8, 7, "Quantum-Secure Email Client", align="L")

    # Version string — right-aligned in the header.
    pdf.set_xy(_PAGE_MARGIN_MM + 4, 28)
    pdf.cell(_CONTENT_WIDTH_MM - 8, 7, f"v{APP_VERSION}", align="R")


def _draw_title_block(pdf: FPDF) -> None:
    """Render the 'Encryption Certificate' title and teal accent bar below the header."""
    # Teal accent bar.
    r, g, b = _COLOUR_ACCENT_TEAL
    pdf.set_fill_color(r, g, b)
    pdf.rect(_PAGE_MARGIN_MM, 43, _CONTENT_WIDTH_MM, 1.5, style="F")

    # Title text.
    r, g, b = _COLOUR_DEEP_BLUE
    pdf.set_text_color(r, g, b)
    pdf.set_font(_FONT_FAMILY, style="B", size=14)
    pdf.set_xy(_PAGE_MARGIN_MM, 48)
    pdf.cell(_CONTENT_WIDTH_MM, 9, "Encryption Certificate", align="C")

    # Subtitle clarification.
    r, g, b = _COLOUR_LABEL_GREY
    pdf.set_text_color(r, g, b)
    pdf.set_font(_FONT_FAMILY, size=8)
    pdf.set_xy(_PAGE_MARGIN_MM, 57)
    pdf.cell(
        _CONTENT_WIDTH_MM,
        5,
        "Cryptographic audit record generated automatically on message send.",
        align="C",
    )


def _draw_fields(pdf: FPDF, cert: dict) -> None:
    """
    Render each certificate field as a label/value row with alternating backgrounds.

    Fields are drawn in the order specified by _FIELD_ORDER.
    Fields whose key is absent from the cert dict are skipped silently.
    """
    row_height = 12
    label_col_w = 52
    value_col_w = _CONTENT_WIDTH_MM - label_col_w
    start_y = 66

    for idx, (key, label) in enumerate(_FIELD_ORDER):
        if key not in cert:
            continue

        raw_value = cert[key]
        # TQR level rendered as "Level N" for clarity.
        if key == "tqr_level":
            display_value = f"Level {raw_value}"
        # Absent key_id (Level 3) rendered as a clear indicator.
        elif key == "key_id" and raw_value == "":
            display_value = "N/A (ML-KEM - no QKD key)"
        else:
            display_value = str(raw_value)

        row_y = start_y + idx * row_height

        # Alternating row background.
        if idx % 2 == 0:
            r, g, b = _COLOUR_LIGHT_BG
            pdf.set_fill_color(r, g, b)
            pdf.rect(_PAGE_MARGIN_MM, row_y, _CONTENT_WIDTH_MM, row_height, style="F")

        # Label.
        r, g, b = _COLOUR_LABEL_GREY
        pdf.set_text_color(r, g, b)
        pdf.set_font(_FONT_FAMILY, style="B", size=8)
        pdf.set_xy(_PAGE_MARGIN_MM + 3, row_y + 2)
        pdf.cell(label_col_w - 3, row_height - 4, label.upper(), align="L")

        # Value — multi_cell used for long strings (e.g. recipient_hash, algorithm).
        r, g, b = _COLOUR_VALUE_BLACK
        pdf.set_text_color(r, g, b)
        pdf.set_font(_FONT_FAMILY, size=8)
        pdf.set_xy(_PAGE_MARGIN_MM + label_col_w, row_y + 2)
        pdf.multi_cell(value_col_w, row_height - 4, display_value, align="L")


def _draw_footer(pdf: FPDF, cert: dict) -> None:
    """Render the footer with cert ID and a brief authenticity notice."""
    footer_y = 270  # Near bottom of A4 page (297 mm tall).

    r, g, b = _COLOUR_ACCENT_TEAL
    pdf.set_fill_color(r, g, b)
    pdf.rect(_PAGE_MARGIN_MM, footer_y, _CONTENT_WIDTH_MM, 0.8, style="F")

    r, g, b = _COLOUR_LABEL_GREY
    pdf.set_text_color(r, g, b)
    pdf.set_font(_FONT_FAMILY, size=7)

    pdf.set_xy(_PAGE_MARGIN_MM, footer_y + 3)
    pdf.cell(
        _CONTENT_WIDTH_MM,
        4,
        (
            "This certificate is an automated audit record produced by QuMail. "
            "It does not constitute a legally binding document."
        ),
        align="C",
    )

    cert_id = cert.get("cert_id", "")
    pdf.set_xy(_PAGE_MARGIN_MM, footer_y + 8)
    pdf.cell(_CONTENT_WIDTH_MM, 4, f"Cert ID: {cert_id}", align="C")


def _build_pdf(cert: dict) -> FPDF:
    """
    Construct and return a fully-rendered FPDF object for the given cert dict.

    Layout (A4, portrait):
      - Branded header with app name and version
      - Teal accent bar + 'Encryption Certificate' title
      - Alternating-row field table for all certificate data
      - Footer with cert ID and disclaimer
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(_PAGE_MARGIN_MM, 10, _PAGE_MARGIN_MM)
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    _draw_header(pdf)
    _draw_title_block(pdf)
    _draw_fields(pdf, cert)
    _draw_footer(pdf, cert)

    return pdf


# --- Public Interface ---

def export(json_path: str) -> str:
    """
    Convert a QuMail JSON encryption certificate to a formatted PDF.

    Reads the certificate JSON from json_path (the path returned by
    cert_generator.generate()), renders a single-page PDF in the same
    directory, and returns the absolute path of the written PDF file.

    The output filename mirrors the input: qumail_cert_{cert_id}.pdf

    Args:
        json_path: Absolute path to the JSON certificate file.

    Returns:
        Absolute path to the written PDF file.

    Raises:
        PdfExportError: If the JSON file cannot be read, is malformed,
                        or if writing the PDF fails.
    """
    cert     = _load_cert(json_path)
    pdf      = _build_pdf(cert)
    pdf_path = _pdf_path_from_json(json_path)

    try:
        pdf.output(pdf_path)
    except OSError as exc:
        raise PdfExportError(
            f"Failed to write PDF to '{pdf_path}': {exc}"
        ) from exc

    return os.path.abspath(pdf_path)
