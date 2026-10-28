"""
Document processing service.
Handles PDF, DOCX, XLSX, CSV, PPTX, and TXT files.
Extracts text, then chunks it using LangChain's RecursiveCharacterTextSplitter.
"""
import io
import logging
import re
from pathlib import Path
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LCDocument

logger = logging.getLogger(__name__)


def _ocr_page(page) -> str:
    """Run OCR on a PDF page using RapidOCR or pytesseract."""
    try:
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
    except Exception as e:
        logger.warning(f"Failed to render page pixmap for OCR: {e}")
        return ""

    # Primary: RapidOCR (onnxruntime, no external binary required)
    try:
        from rapidocr_onnxruntime import RapidOCR
        ocr = RapidOCR()
        res, _ = ocr(img_bytes)
        if res:
            lines = [line[1] for line in res if line and len(line) > 1 and line[1].strip()]
            if lines:
                return "\n".join(lines)
    except ImportError:
        logger.debug("rapidocr_onnxruntime not installed")
    except Exception as e:
        logger.warning(f"RapidOCR recognition error: {e}")

    # Fallback: pytesseract
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img)
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.debug(f"pytesseract recognition error: {e}")

    return ""


def _extract_pdf(file_path: Path) -> str:
    """Extract text from a PDF using PyMuPDF (fitz) with OCR support for scanned/image pages."""
    pages = []
    ocr_used = False
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(file_path))
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text").strip()
            # If page contains little or no text, attempt OCR
            if not text:
                ocr_text = _ocr_page(page)
                if ocr_text:
                    text = ocr_text
                    ocr_used = True
                    logger.info(f"Page {page_num} extracted via OCR in {file_path.name}")
            if text:
                pages.append(f"[Page {page_num}]\n{text}")
        doc.close()
        result = "\n\n".join(pages)
        if result.strip():
            if ocr_used:
                logger.info(f"Extracted {len(pages)} pages (including OCR) from {file_path.name}")
            else:
                logger.info(f"Extracted {len(pages)} pages from PDF using PyMuPDF")
            return result
        logger.warning("PyMuPDF (and OCR) returned empty text, trying fallback parsers...")
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed: {e}, trying fallback parsers...")

    # Fallback to pdfplumber
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text and text.strip():
                    pages.append(f"[Page {page_num}]\n{text.strip()}")
        result = "\n\n".join(pages)
        if result.strip():
            logger.info(f"Extracted {len(pages)} pages from PDF using pdfplumber")
            return result
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}, trying pypdf...")

    # Final fallback to pypdf / PyPDF2
    try:
        import pypdf
        pages = []
        reader = pypdf.PdfReader(str(file_path))
        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                pages.append(f"[Page {page_num}]\n{text.strip()}")
        result = "\n\n".join(pages)
        if result.strip():
            logger.info(f"Extracted {len(pages)} pages from PDF using pypdf")
            return result
    except Exception as e:
        logger.warning(f"pypdf extraction failed: {e}")

    raise ValueError(
        f"No extractable text found in PDF '{file_path.name}'. "
        "The document is empty or scanned text could not be recognized."
    )


def _extract_docx(file_path: Path) -> str:
    """Extract text from a Word document."""
    try:
        from docx import Document
        doc = Document(str(file_path))
        sections = []
        for para in doc.paragraphs:
            if para.text.strip():
                sections.append(para.text)
        # Extract table content too
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    sections.append(row_text)
        return "\n".join(sections)
    except Exception as e:
        logger.error(f"DOCX extraction failed for {file_path}: {e}")
        raise


def _extract_xlsx(file_path: Path) -> str:
    """Extract text and data from an Excel workbook."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
        sheets_text = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows_text = []
            for row in ws.iter_rows(values_only=True):
                row_vals = [str(v) for v in row if v is not None]
                if row_vals:
                    rows_text.append(" | ".join(row_vals))
            if rows_text:
                sheets_text.append(f"[Sheet: {sheet_name}]\n" + "\n".join(rows_text))
        wb.close()
        return "\n\n".join(sheets_text)
    except Exception as e:
        logger.error(f"XLSX extraction failed for {file_path}: {e}")
        raise


def _extract_csv(file_path: Path) -> str:
    """Extract text from a CSV file."""
    try:
        import pandas as pd
        df = pd.read_csv(str(file_path))
        lines = [" | ".join(str(v) for v in df.columns)]
        for _, row in df.iterrows():
            lines.append(" | ".join(str(v) for v in row.values))
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"CSV extraction failed for {file_path}: {e}")
        raise


def _extract_pptx(file_path: Path) -> str:
    """Extract text from a PowerPoint presentation."""
    try:
        from pptx import Presentation
        prs = Presentation(str(file_path))
        slides_text = []
        for slide_num, slide in enumerate(prs.slides, 1):
            texts = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    texts.append(shape.text.strip())
            if texts:
                slides_text.append(f"[Slide {slide_num}]\n" + "\n".join(texts))
        return "\n\n".join(slides_text)
    except Exception as e:
        logger.error(f"PPTX extraction failed for {file_path}: {e}")
        raise


def _extract_txt(file_path: Path) -> str:
    """Read plain text file."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode text file: {file_path}")


def _try_libreoffice_conversion(file_path: Path, target_ext: str) -> Optional[Path]:
    """Attempt conversion of legacy format using LibreOffice/soffice if available."""
    import shutil
    import subprocess
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    try:
        out_dir = file_path.parent
        cmd = [soffice, "--headless", "--convert-to", target_ext, str(file_path), "--outdir", str(out_dir)]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        converted = file_path.with_suffix(f".{target_ext}")
        if converted.exists():
            return converted
    except Exception as e:
        logger.warning(f"LibreOffice conversion failed for {file_path}: {e}")
    return None


def _extract_legacy_doc(file_path: Path) -> str:
    """Extract text from legacy Word .doc format using LibreOffice or olefile."""
    converted = _try_libreoffice_conversion(file_path, "docx")
    if converted:
        try:
            return _extract_docx(converted)
        finally:
            converted.unlink(missing_ok=True)

    try:
        import olefile
        import re
        if olefile.isOleFile(str(file_path)):
            ole = olefile.OleFileIO(str(file_path))
            if ole.exists('WordDocument'):
                stream = ole.openstream('WordDocument').read()
                raw_text = stream.decode('utf-16le', errors='ignore')
                clean_lines = [line.strip() for line in re.split(r'[\r\n\x00-\x08\x0b\x0c\x0e-\x1f]+', raw_text) if len(line.strip()) > 3]
                if len(clean_lines) >= 2:
                    return "\n".join(clean_lines)
                raw_ascii = stream.decode('latin-1', errors='ignore')
                clean_lines = [line.strip() for line in re.split(r'[\r\n\x00-\x08\x0b\x0c\x0e-\x1f]+', raw_ascii) if len(line.strip()) > 3]
                if len(clean_lines) >= 2:
                    return "\n".join(clean_lines)
    except Exception as e:
        logger.warning(f"olefile extraction failed for {file_path}: {e}")

    raise ValueError(
        f"Legacy Microsoft Word format (.doc) could not be extracted directly. "
        f"Please save '{file_path.name}' as modern Word format (.docx) or PDF."
    )


def _extract_legacy_xls(file_path: Path) -> str:
    """Extract text from legacy Excel .xls format using xlrd or LibreOffice."""
    try:
        import xlrd
        wb = xlrd.open_workbook(str(file_path))
        sheets_text = []
        for sheet_idx in range(wb.nsheets):
            ws = wb.sheet_by_index(sheet_idx)
            rows_text = []
            for row_idx in range(ws.nrows):
                row_vals = [str(ws.cell_value(row_idx, col_idx)) for col_idx in range(ws.ncols) if ws.cell_value(row_idx, col_idx) != ""]
                if row_vals:
                    rows_text.append(" | ".join(row_vals))
            if rows_text:
                sheets_text.append(f"[Sheet: {ws.name}]\n" + "\n".join(rows_text))
        if sheets_text:
            return "\n\n".join(sheets_text)
    except Exception as e:
        logger.warning(f"xlrd extraction failed for {file_path}: {e}")

    converted = _try_libreoffice_conversion(file_path, "xlsx")
    if converted:
        try:
            return _extract_xlsx(converted)
        finally:
            converted.unlink(missing_ok=True)

    raise ValueError(
        f"Legacy Microsoft Excel format (.xls) extraction failed. "
        f"Please save or convert '{file_path.name}' to modern Excel format (.xlsx) or CSV."
    )


def _extract_legacy_ppt(file_path: Path) -> str:
    """Extract text from legacy PowerPoint .ppt format, or reject with clear actionable error."""
    converted = _try_libreoffice_conversion(file_path, "pptx")
    if converted:
        try:
            return _extract_pptx(converted)
        finally:
            converted.unlink(missing_ok=True)

    raise ValueError(
        f"Legacy Microsoft PowerPoint format (.ppt) is not supported directly. "
        f"Please convert '{file_path.name}' to modern PowerPoint format (.pptx) or PDF before uploading."
    )


def _extract_image(file_path: Path) -> str:
    """Extract text from an image file (PNG, JPG, JPEG) using OCR."""
    img_bytes = file_path.read_bytes()
    try:
        from rapidocr_onnxruntime import RapidOCR
        ocr = RapidOCR()
        res, _ = ocr(img_bytes)
        if res:
            return "\n".join(line[1] for line in res if line and len(line) > 1 and line[1].strip())
    except Exception as e:
        logger.debug(f"RapidOCR image extraction error: {e}")

    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img)
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.debug(f"pytesseract image extraction error: {e}")

    raise ValueError(f"Could not extract any text from image '{file_path.name}'. Ensure it contains readable text.")


# ── Dispatcher ────────────────────────────────────────────────────────────────

EXTRACTORS = {
    "pdf": _extract_pdf,
    "docx": _extract_docx,
    "doc": _extract_legacy_doc,
    "xlsx": _extract_xlsx,
    "xls": _extract_legacy_xls,
    "csv": _extract_csv,
    "pptx": _extract_pptx,
    "ppt": _extract_legacy_ppt,
    "txt": _extract_txt,
    "md": _extract_txt,
    "json": _extract_txt,
    "html": _extract_txt,
    "htm": _extract_txt,
    "py": _extract_txt,
    "java": _extract_txt,
    "c": _extract_txt,
    "cpp": _extract_txt,
    "rtf": _extract_txt,
    "png": _extract_image,
    "jpg": _extract_image,
    "jpeg": _extract_image,
}


def extract_text(file_path: Path, file_type: str) -> str:
    """Dispatch to the correct extractor based on file type."""
    extractor = EXTRACTORS.get(file_type.lower())
    if extractor is None:
        raise ValueError(f"Unsupported file type: {file_type}")
    return extractor(file_path)


def _looks_like_heading(line: str) -> bool:
    """Return True for section headings such as 'What is DATA?' or 'Definition of Big data'."""
    line = line.strip()
    if not line:
        return False
    if line.startswith("[Page") or line.startswith("Page ") or line.startswith("Fig:"):
        return False
    lowered = line.lower()
    if lowered.startswith(("what is", "definition of", "classification", "characteristics", "why", "types", "advantages", "disadvantages", "features", "importance", "example", "typical")):
        return True
    return line.endswith("?") or line.endswith(":")


def _enrich_chunk_with_heading(chunk: str) -> tuple[str, Optional[str]]:
    """Prefix a chunk with its nearest heading so embeddings are more specific."""
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    heading = None
    for line in lines:
        if _looks_like_heading(line):
            heading = line
            break

    if heading and f"Section: {heading}" not in chunk:
        return f"Section: {heading}\n{chunk}", heading
    return chunk, heading


def chunk_text(
    text: str,
    doc_id: int,
    filename: str,
    workspace_id: int,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[LCDocument]:
    """
    Split extracted text into overlapping chunks.
    Returns LangChain Document objects with metadata.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_text(text)
    documents = []
    for idx, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        enriched_chunk, heading = _enrich_chunk_with_heading(chunk)
        documents.append(
            LCDocument(
                page_content=enriched_chunk,
                metadata={
                    "doc_id": doc_id,
                    "filename": filename,
                    "workspace_id": workspace_id,
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                    "section_heading": heading,
                },
            )
        )
    return documents


def process_document(
    file_path: Path,
    file_type: str,
    doc_id: int,
    filename: str,
    workspace_id: int,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[LCDocument]:
    """
    Full pipeline: extract → chunk → return LangChain documents.
    """
    logger.info(f"Processing {filename} ({file_type}) doc_id={doc_id}")
    text = extract_text(file_path, file_type)
    if not text.strip():
        raise ValueError(f"No extractable text found in {filename}")
    chunks = chunk_text(
        text, doc_id, filename, workspace_id, chunk_size, chunk_overlap
    )
    logger.info(f"Produced {len(chunks)} chunks from {filename}")
    return chunks
