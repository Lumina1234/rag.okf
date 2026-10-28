import pytest
import io
import fitz
from pathlib import Path
from PIL import Image, ImageDraw

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services import document_processor


def test_legacy_format_rejection(tmp_path):
    """Test that legacy .doc, .xls, .ppt raise clear actionable errors when LibreOffice is unavailable."""
    doc_file = tmp_path / "test.doc"
    doc_file.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") # OLE2 header

    xls_file = tmp_path / "test.xls"
    xls_file.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")

    ppt_file = tmp_path / "test.ppt"
    ppt_file.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")

    with pytest.raises(ValueError) as exc1:
        document_processor.extract_text(doc_file, "doc")
    assert "Legacy Microsoft Word format (.doc)" in str(exc1.value)
    assert ".docx" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        document_processor.extract_text(xls_file, "xls")
    assert "Legacy Microsoft Excel format (.xls)" in str(exc2.value)
    assert ".xlsx" in str(exc2.value)

    with pytest.raises(ValueError) as exc3:
        document_processor.extract_text(ppt_file, "ppt")
    assert "Legacy Microsoft PowerPoint format (.ppt)" in str(exc3.value)
    assert ".pptx" in str(exc3.value)


def test_scanned_pdf_ocr_extraction(tmp_path):
    """Test OCR extraction on an image-only (scanned) PDF page."""
    # Create an image containing recognizable text
    img = Image.new('RGB', (450, 100), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((15, 25), "Scanned Invoice ABC-12345", fill=(0, 0, 0))

    img_buf = io.BytesIO()
    img.save(img_buf, format='PNG')
    img_bytes = img_buf.getvalue()

    # Create PDF with the scanned image
    pdf_path = tmp_path / "scanned_doc.pdf"
    doc = fitz.open()
    page = doc.new_page(width=450, height=100)
    page.insert_image(page.rect, stream=img_bytes)
    doc.save(str(pdf_path))
    doc.close()

    # Extract text using document_processor
    text = document_processor.extract_text(pdf_path, "pdf")

    assert "[Page 1]" in text
    assert ("Invoice" in text or "ABC" in text or "12345" in text), f"OCR failed to recognize text: {text}"


def test_mixed_pdf_extraction(tmp_path):
    """Test mixed PDF containing one text page and one scanned image page."""
    pdf_path = tmp_path / "mixed_doc.pdf"
    doc = fitz.open()

    # Page 1: Digital text
    page1 = doc.new_page(width=400, height=100)
    page1.insert_text((20, 40), "Digital Page One Text Content")

    # Page 2: Image-only (scanned)
    img = Image.new('RGB', (400, 100), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((15, 25), "Receipt Total USD 500", fill=(0, 0, 0))
    img_buf = io.BytesIO()
    img.save(img_buf, format='PNG')

    page2 = doc.new_page(width=400, height=100)
    page2.insert_image(page2.rect, stream=img_buf.getvalue())

    doc.save(str(pdf_path))
    doc.close()

    text = document_processor.extract_text(pdf_path, "pdf")

    assert "[Page 1]" in text
    assert "Digital Page One Text Content" in text
    assert "[Page 2]" in text
    assert ("Receipt" in text or "Total" in text or "500" in text)


def test_empty_pdf_rejection(tmp_path):
    """Test that a completely blank PDF raises ValueError and is not silently indexed."""
    blank_pdf = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=300) # completely blank page
    doc.save(str(blank_pdf))
    doc.close()

    with pytest.raises(ValueError) as exc:
        document_processor.extract_text(blank_pdf, "pdf")
    assert "No extractable text found in PDF" in str(exc.value)
