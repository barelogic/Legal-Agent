"""PDF text extraction: PyMuPDF first, OCR fallback for scanned pages.

Pages with almost no extractable text are rendered at 300 DPI and passed
through Tesseract (if installed). Missing tools degrade to empty text
rather than crashing, so ingest keeps working end-to-end.
"""

import shutil
from pathlib import Path

#: Pages with fewer chars than this are treated as scanned and sent to OCR.
MIN_CHARS_FOR_TEXT_PAGE = 30


def _ocr_page(page) -> str:
    """OCR one PyMuPDF page; "" when tesseract/pillow are unavailable."""
    if shutil.which("tesseract") is None:
        return ""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return pytesseract.image_to_string(img) or ""
    except Exception:
        return ""


def extract_pages(path: str | Path) -> list[tuple[int, str]]:
    """Return [(page_no, text)] for a PDF; OCR fallback for scanned pages."""
    try:
        import fitz
    except ImportError as e:
        raise RuntimeError("PyMuPDF is not installed (pip install pymupdf)") from e
    out: list[tuple[int, str]] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            try:
                text = page.get_text() or ""
            except Exception:
                text = ""
            if len(text.strip()) < MIN_CHARS_FOR_TEXT_PAGE:
                ocr = _ocr_page(page)
                if len(ocr.strip()) > len(text.strip()):
                    text = ocr
            out.append((i, text))
    return out


def read_text_file(path: str | Path) -> list[tuple[int, str]]:
    """Read a .txt file as a single page (uniform interface with PDFs)."""
    return [(1, Path(path).read_text(encoding="utf-8"))]
