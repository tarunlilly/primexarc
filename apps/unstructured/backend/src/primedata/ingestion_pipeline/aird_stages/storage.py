"""
S3/GCS storage adapter for AIRD pipeline stages.

Provides file-like operations that map AIRD's local filesystem patterns
to PrimeData's S3/GCS object storage.
"""

import json
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from primedata.utils.logger import get_logger
from primedata.storage.storage_client import storage_client
from primedata.storage.paths import (
    chunk_prefix,
    clean_prefix,
    raw_prefix,
    artifacts_prefix,
    safe_filename,
)

logger = get_logger(__name__)


class AirdStorageAdapter:
    """Adapter that provides AIRD-compatible file operations using S3/GCS.

    Maps AIRD's local filesystem patterns to S3/GCS storage:
    - data/raw/{stem}.txt → S3/GCS raw bucket
    - data/processed/{stem}.jsonl → S3/GCS processed bucket
    - data/processed/metrics.json → S3/GCS processed bucket
    """

    def __init__(
        self,
        workspace_id: UUID,
        product_id: UUID,
        version: int,
    ):
        """Initialize storage adapter.

        Args:
            workspace_id: Workspace UUID
            product_id: Product UUID
            version: Product version number
        """
        self.workspace_id = workspace_id
        self.product_id = product_id
        self.version = version
        self.storage_client = storage_client
        # Use module-level logger (Python's built-in logging)
        self.logger = logger
        logger.info(f"🎯 AirdStorageAdapter.__init__() entry | workspace={workspace_id}, product={product_id}, version={version}")
        self.logger.debug(f"🔧 AirdStorageAdapter initialized | workspace={workspace_id}, product={product_id}, version={version}")

    def _get_s3_bucket(self) -> str:
        """Get S3 bucket from environment, fall back to primedata-raw for legacy."""
        return os.getenv("S3_METADATA_BUCKET", "primedata-raw")

    def _get_metadata_path(self) -> str:
        """Get metadata path from environment."""
        path = os.getenv("S3_METADATA_PATH", "")
        if path and not path.endswith("/"):
            path += "/"
        return path

    def _build_s3_key(self, subfolder: str, relative_key: str) -> str:
        """Build full S3 key with metadata path and subfolder.

        Ensures the key doesn't double-prepend the metadata path.

        Args:
            subfolder: Subfolder name (raw, clean, chunk, exports, config)
            relative_key: The relative key/path within the subfolder

        Returns:
            Full S3 key ready for storage_client
        """
        metadata_path = self._get_metadata_path()

        # Check if key already starts with metadata_path (prevent double-prepending)
        if metadata_path and relative_key.startswith(metadata_path):
            self.logger.debug(f"🔍 Key already contains metadata path, using as-is: {relative_key}")
            return relative_key

        # Build the full key: metadata_path + subfolder + relative_key
        full_key = f"{metadata_path}{subfolder}/{relative_key}"
        self.logger.debug(f"🔨 Built S3 key | metadata_path={metadata_path}, subfolder={subfolder}, full_key={full_key}")
        return full_key

    def _get_raw_prefix(self) -> str:
        """Get S3/GCS prefix for raw data."""
        return raw_prefix(self.workspace_id, self.product_id, self.version)

    def _get_processed_prefix(self) -> str:
        """Get S3/GCS prefix for processed data."""
        return clean_prefix(self.workspace_id, self.product_id, self.version)

    def _get_chunk_prefix(self) -> str:
        """Get S3/GCS prefix for chunked data."""
        return chunk_prefix(self.workspace_id, self.product_id, self.version)

    def put_raw_text(self, stem: str, text: str) -> str:
        """Store raw text file (equivalent to data/raw/{stem}.txt).

        Args:
            stem: File stem (without extension)
            text: Text content

        Returns:
            S3/GCS object key
        """
        relative_key = f"{self._get_raw_prefix()}{safe_filename(stem)}.txt"
        full_key = self._build_s3_key("raw", relative_key)
        self.logger.debug(f"📤 Storing raw text | stem={stem}, key={full_key}, size={len(text)} bytes")
        success = self.storage_client.put_bytes(
            bucket=self._get_s3_bucket(),
            key=full_key,
            data=text.encode("utf-8"),
            content_type="text/plain",
        )
        if not success:
            self.logger.error(f"❌ Failed to store raw text: {full_key}")
            raise RuntimeError(f"Failed to store raw text: {full_key}")
        self.logger.info(f"✅ Stored raw text: {full_key} ({len(text)} chars)")
        return full_key

    def put_manifest(self, stem: str, manifest: Dict[str, Any]) -> str:
        """Store manifest JSON (equivalent to data/raw/{stem}.manifest.json).

        Args:
            stem: File stem
            manifest: Manifest dictionary

        Returns:
            S3/GCS object key
        """
        relative_key = f"{self._get_raw_prefix()}{safe_filename(stem)}.manifest.json"
        full_key = self._build_s3_key("raw", relative_key)
        self.logger.debug(f"📤 Storing manifest | stem={stem}, key={full_key}, entries={len(manifest)}")
        success = self.storage_client.put_json(
            bucket=self._get_s3_bucket(),
            key=full_key,
            obj=manifest,
        )
        if not success:
            self.logger.error(f"❌ Failed to store manifest: {full_key}")
            raise RuntimeError(f"Failed to store manifest: {full_key}")
        self.logger.info(f"✅ Stored manifest: {full_key} ({len(manifest)} entries)")
        return full_key

    def put_processed_jsonl(self, stem: str, records: List[Dict[str, Any]]) -> str:
        """Store processed JSONL file (equivalent to data/processed/{stem}.jsonl).

        Args:
            stem: File stem
            records: List of record dictionaries

        Returns:
            S3/GCS object key
        """
        relative_key = f"{self._get_processed_prefix()}{safe_filename(stem)}.jsonl"
        full_key = self._build_s3_key("clean", relative_key)
        # Convert records to JSONL format (one JSON object per line)
        jsonl_content = "\n".join(json.dumps(rec, ensure_ascii=False) for rec in records)
        self.logger.debug(f"📤 Storing processed JSONL | stem={stem}, key={full_key}, records={len(records)}, size={len(jsonl_content)} bytes")
        success = self.storage_client.put_bytes(
            bucket=self._get_s3_bucket(),
            key=full_key,
            data=jsonl_content.encode("utf-8"),
            content_type="application/x-ndjson",
        )
        if not success:
            self.logger.error(f"❌ Failed to store processed JSONL: {full_key}")
            raise RuntimeError(f"Failed to store processed JSONL: {full_key}")
        self.logger.info(f"✅ Stored processed JSONL: {full_key} ({len(records)} records, {len(jsonl_content)} bytes)")
        return full_key

    def put_metrics_json(self, metrics: List[Dict[str, Any]]) -> str:
        """Store metrics JSON (equivalent to data/processed/metrics.json).

        Args:
            metrics: List of metric dictionaries

        Returns:
            S3/GCS object key
        """
        relative_key = f"{self._get_processed_prefix()}metrics.json"
        full_key = self._build_s3_key("clean", relative_key)
        self.logger.debug(f"📤 Storing metrics JSON | key={full_key}, entries={len(metrics)}")
        success = self.storage_client.put_json(
            bucket=self._get_s3_bucket(),
            key=full_key,
            obj=metrics,
        )
        if not success:
            self.logger.error(f"❌ Failed to store metrics: {full_key}")
            raise RuntimeError(f"Failed to store metrics: {full_key}")
        self.logger.info(f"✅ Stored metrics: {full_key} ({len(metrics)} entries)")
        return full_key

    def get_raw_text(self, stem: str, storage_key: Optional[str] = None, storage_bucket: Optional[str] = None) -> Optional[str]:
        """Retrieve raw text file.

        Supports both text files and binary files (PDFs) with automatic format detection.

        Args:
            stem: File stem (for backward compatibility)
            storage_key: Optional exact S3/GCS key from database (takes precedence)
            storage_bucket: Optional bucket name (defaults to S3_METADATA_BUCKET or primedata-raw)

        Returns:
            Text content, or None if not found
        """
        # If exact storage_key provided (from database), use it directly
        if storage_key:
            bucket = storage_bucket or self._get_s3_bucket()
            # Use both loguru and std logging for Airflow visibility
            self.logger.info(f"[get_raw_text] Attempting to fetch from S3/GCS: bucket={bucket}, key={storage_key}")
            try:
                # Log before calling get_bytes
                self.logger.info(f"[get_raw_text] Calling storage_client.get_bytes(bucket={bucket}, key={storage_key})")
                data = self.storage_client.get_bytes(bucket, storage_key)
                self.logger.info(
                    f"[get_raw_text] get_bytes() returned: type={type(data)}, value={'None' if data is None else f'{len(data)} bytes'}"
                )

                if data is None:
                    error_msg = f"[get_raw_text] Failed to retrieve file from S3/GCS: bucket={bucket}, key={storage_key} - file does not exist or access denied"
                    self.logger.error(error_msg)
                    return None

                success_msg = f"[get_raw_text] Successfully retrieved {len(data)} bytes from S3/GCS: {storage_key}"
                self.logger.info(success_msg)

                # Try to decode as text first
                try:
                    decoded_text = data.decode("utf-8")
                    decode_success_msg = f"[get_raw_text] Successfully decoded as UTF-8 text ({len(decoded_text)} characters)"
                    self.logger.info(decode_success_msg)
                    return decoded_text
                except UnicodeDecodeError:
                    self.logger.info(f"[get_raw_text] File is not UTF-8 text (binary detected). Attempting conversion/extraction...")
                    # Binary file detected - try PDF/DOCX extraction/conversion

                    # Check if DOCX/DOC file
                    if storage_key.lower().endswith((".docx", ".doc")):
                        try:
                            self.logger.info(f"[get_raw_text] Detected DOCX/DOC file, converting to PDF for extraction: {storage_key} (size: {len(data)} bytes)")
                            # Convert to PDF first
                            pdf_data = self._convert_docx_to_pdf(data, storage_key)
                            # Then extract text from PDF
                            extracted_text = self._extract_pdf_text(pdf_data)
                            if extracted_text and extracted_text.strip():
                                success_msg = f"[get_raw_text] Successfully converted and extracted {len(extracted_text)} characters from DOCX/DOC: {storage_key}"
                                self.logger.info(success_msg)
                                return extracted_text
                            else:
                                warn_msg = f"[get_raw_text] DOCX/DOC extraction returned empty text for {storage_key}"
                                self.logger.warning(warn_msg)
                                return None
                        except Exception as docx_exc:
                            error_msg = (
                                f"[get_raw_text] Exception during DOCX/DOC conversion for {storage_key}: {type(docx_exc).__name__}: {str(docx_exc)}"
                            )
                            self.logger.error(error_msg, exc_info=True)
                            import traceback
                            tb = traceback.format_exc()
                            self.logger.error(f"[get_raw_text] DOCX/DOC conversion traceback:\n{tb}")
                            return None

                    # Check if PDF file
                    elif storage_key.lower().endswith(".pdf"):
                        try:
                            # Use both loguru and std logging for Airflow visibility
                            log_msg = (
                                f"[get_raw_text] Attempting to extract text from PDF: {storage_key} (size: {len(data)} bytes)"
                            )
                            self.logger.info(log_msg)
                            extracted_text = self._extract_pdf_text(data)
                            if extracted_text and extracted_text.strip():
                                success_msg = f"[get_raw_text] Successfully extracted {len(extracted_text)} characters from PDF: {storage_key}"
                                self.logger.info(success_msg)
                                return extracted_text
                            else:
                                warn_msg = f"[get_raw_text] PDF extraction returned empty text for {storage_key} - PDF may be image-based, encrypted, or corrupted"
                                self.logger.warning(warn_msg)
                                return None
                        except Exception as pdf_exc:
                            error_msg = (
                                f"[get_raw_text] Exception during PDF extraction for {storage_key}: {type(pdf_exc).__name__}: {str(pdf_exc)}"
                            )
                            self.logger.error(error_msg, exc_info=True)
                            import traceback

                            tb = traceback.format_exc()
                            self.logger.error(f"[get_raw_text] PDF extraction traceback:\n{tb}")
                            return None
                    else:
                        warn_msg = f"[get_raw_text] Failed to decode file {storage_key} as UTF-8 and it's not a PDF/DOCX/DOC file (extension: {storage_key.split('.')[-1] if '.' in storage_key else 'none'})"
                        self.logger.warning(warn_msg)
                        return None
            except Exception as e:
                error_msg = f"[get_raw_text] Unexpected exception while fetching from S3/GCS (bucket={bucket}, key={storage_key}): {type(e).__name__}: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                import traceback

                tb = traceback.format_exc()
                self.logger.error(f"[get_raw_text] S3/GCS fetch traceback:\n{tb}")
                return None

        # Fallback: Try to construct path with .txt extension (original behavior)
        relative_key = f"{self._get_raw_prefix()}{safe_filename(stem)}.txt"
        full_key = self._build_s3_key("raw", relative_key)
        data = self.storage_client.get_bytes(self._get_s3_bucket(), full_key)
        if data is None:
            return None
        return data.decode("utf-8")

    def _convert_docx_to_pdf(self, docx_data: bytes, filename: str) -> bytes:
        """Convert DOCX/DOC file to PDF for text extraction.

        Args:
            docx_data: DOCX/DOC file content as bytes
            filename: Original filename (for logging)

        Returns:
            PDF file content as bytes
        """
        from io import BytesIO

        self.logger.info(f"[_convert_docx_to_pdf] ⏳ START: Converting {filename} to PDF")
        self.logger.info(f"[_convert_docx_to_pdf] Input data size: {len(docx_data)} bytes")

        try:
            from docx import Document
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
            from reportlab.platypus import Image as RLImage
            from reportlab.lib import colors

            self.logger.info(f"[_convert_docx_to_pdf] ✅ Dependencies imported successfully")

            # Parse DOCX
            docx_file = BytesIO(docx_data)
            try:
                doc = Document(docx_file)
                self.logger.info(f"[_convert_docx_to_pdf] ✅ Successfully parsed DOCX document with {len(doc.paragraphs)} paragraphs, {len(doc.tables)} tables")
            except Exception as e:
                self.logger.error(f"[_convert_docx_to_pdf] ❌ Failed to parse DOCX: {type(e).__name__}: {str(e)}", exc_info=True)
                raise ValueError(f"Invalid DOCX file: {str(e)}")

            # Create PDF
            pdf_buffer = BytesIO()
            pdf_doc = SimpleDocTemplate(
                pdf_buffer,
                pagesize=letter,
                rightMargin=0.75 * inch,
                leftMargin=0.75 * inch,
                topMargin=0.75 * inch,
                bottomMargin=0.75 * inch,
            )

            # Extract content from DOCX
            styles = getSampleStyleSheet()
            story = []
            para_count = 0
            table_count = 0

            # Add paragraphs from DOCX
            for para in doc.paragraphs:
                if para.text.strip():
                    # Determine paragraph style based on DOCX formatting
                    style_name = "Normal"
                    if para.style:
                        if "Heading" in para.style.name:
                            style_name = "Heading1"
                        elif para.runs and para.runs[0].bold:
                            style_name = "Heading2"

                    paragraph = Paragraph(para.text, styles[style_name])
                    story.append(paragraph)
                    story.append(Spacer(1, 0.2 * inch))
                    para_count += 1
                else:
                    # Preserve empty lines
                    story.append(Spacer(1, 0.1 * inch))

            self.logger.info(f"[_convert_docx_to_pdf] ✅ Added {para_count} paragraphs to story")

            # Add tables if present in DOCX
            for table in doc.tables:
                table_data = []
                for row in table.rows:
                    row_data = []
                    for cell in row.cells:
                        row_data.append(Paragraph(cell.text or "", styles["Normal"]))
                    table_data.append(row_data)

                if table_data:
                    pdf_table = Table(table_data)
                    pdf_table.setStyle(
                        TableStyle([
                            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 12),
                            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                            ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ])
                    )
                    story.append(pdf_table)
                    story.append(Spacer(1, 0.3 * inch))
                    table_count += 1

            self.logger.info(f"[_convert_docx_to_pdf] ✅ Added {table_count} tables to story")

            # Check if story has content
            if not story:
                self.logger.warning(f"[_convert_docx_to_pdf] ⚠️ Story is empty - no content to convert")
                raise ValueError("DOCX document has no extractable content")

            # Build PDF
            try:
                pdf_doc.build(story)
                self.logger.info(f"[_convert_docx_to_pdf] ✅ PDF built successfully")
            except Exception as e:
                self.logger.error(f"[_convert_docx_to_pdf] ❌ Failed to build PDF: {type(e).__name__}: {str(e)}", exc_info=True)
                raise

            pdf_buffer.seek(0)
            pdf_content = pdf_buffer.getvalue()

            self.logger.info(f"[_convert_docx_to_pdf] ✅ COMPLETE: Successfully converted to PDF ({len(pdf_content)} bytes)")
            return pdf_content

        except ImportError as e:
            error_msg = f"[_convert_docx_to_pdf] ❌ Missing dependency: {e}. Install with: pip install python-docx reportlab"
            self.logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            self.logger.error(f"[_convert_docx_to_pdf] ❌ Conversion failed: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

    def _extract_pdf_text(self, pdf_data: bytes) -> str:
        """Extract text content from PDF bytes.

        Args:
            pdf_data: PDF file content as bytes

        Returns:
            Extracted text content
        """
        from io import BytesIO

        self.logger.info(f"[_extract_pdf_text] Starting PDF text extraction for {len(pdf_data)} bytes")

        try:
            # Try pypdf (modern, actively maintained)
            try:
                from pypdf import PdfReader

                self.logger.info(f"[_extract_pdf_text] Using pypdf library for extraction")

                pdf_file = BytesIO(pdf_data)
                self.logger.info(f"[_extract_pdf_text] Created BytesIO object, attempting to read PDF...")

                try:
                    reader = PdfReader(pdf_file)
                    self.logger.info(
                        f"[_extract_pdf_text] PdfReader created successfully. Number of pages: {len(reader.pages)}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"[_extract_pdf_text] Failed to create PdfReader: {type(e).__name__}: {str(e)}", exc_info=True
                    )
                    import traceback

                    self.logger.error(f"[_extract_pdf_text] PdfReader creation traceback:\n{traceback.format_exc()}")
                    raise

                text_parts = []
                for i, page in enumerate(reader.pages):
                    try:
                        page_text = page.extract_text()
                        # Add page marker for page detection in preprocessing
                        # Format: "=== PAGE N ===" to match page_fences pattern
                        page_marker = f"\n=== PAGE {i+1} ===\n"
                        text_parts.append(page_marker + page_text)
                        self.logger.debug(f"[_extract_pdf_text] Extracted {len(page_text)} characters from page {i+1}")
                    except Exception as e:
                        self.logger.warning(
                            f"[_extract_pdf_text] Failed to extract text from page {i+1}: {type(e).__name__}: {str(e)}"
                        )
                        # Still add page marker even for empty pages
                        page_marker = f"\n=== PAGE {i+1} ===\n"
                        text_parts.append(page_marker)

                extracted_text = "\n".join(text_parts)
                total_msg = f"[_extract_pdf_text] Total extracted text length: {len(extracted_text)} characters"
                self.logger.info(total_msg)

                if not extracted_text.strip():
                    warn_msg = "[_extract_pdf_text] PDF extraction returned empty text - PDF may be image-based, encrypted, or contain no text content"
                    self.logger.warning(warn_msg)
                else:
                    # Show preview of extracted text (skip page markers in preview)
                    preview_text = extracted_text[:200].replace("=== PAGE", "[PAGE").replace("===\n", "]")
                    # Count total pages extracted
                    page_count = extracted_text.count("=== PAGE")
                    success_msg = f"[_extract_pdf_text] Successfully extracted text ({page_count} pages, {len(extracted_text)} chars). Preview: {preview_text}..."
                    self.logger.info(success_msg)

                return extracted_text
            except ImportError:
                # Fallback to PyPDF2 if pypdf not available
                try:
                    from PyPDF2 import PdfReader

                    pdf_file = BytesIO(pdf_data)
                    reader = PdfReader(pdf_file)
                    text_parts = []

                    for page in reader.pages:
                        text_parts.append(page.extract_text())

                    extracted_text = "\n\n".join(text_parts)
                    if not extracted_text.strip():
                        self.logger.warning("PDF extraction returned empty text - PDF may be image-based or encrypted")
                    return extracted_text
                except ImportError:
                    self.logger.error("pypdf/PyPDF2 not installed, cannot extract PDF text")
                    raise ImportError("PDF parsing library (pypdf or PyPDF2) is required for PDF files")
        except Exception as e:
            self.logger.error(f"Error extracting PDF text: {e}", exc_info=True)
            raise

    def get_manifest(self, stem: str) -> Optional[Dict[str, Any]]:
        """Retrieve manifest JSON.

        Args:
            stem: File stem

        Returns:
            Manifest dictionary, or None if not found
        """
        relative_key = f"{self._get_raw_prefix()}{safe_filename(stem)}.manifest.json"
        full_key = self._build_s3_key("raw", relative_key)
        self.logger.debug(f"📥 Retrieving manifest | stem={stem}, key={full_key}")
        result = self.storage_client.get_json(self._get_s3_bucket(), full_key)
        if result:
            self.logger.debug(f"✅ Retrieved manifest | entries={len(result)}")
        else:
            self.logger.debug(f"⚠️ Manifest not found: {full_key}")
        return result

    def get_processed_jsonl(self, stem: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve processed JSONL file.

        Args:
            stem: File stem

        Returns:
            List of record dictionaries, or None if not found
        """
        relative_key = f"{self._get_processed_prefix()}{safe_filename(stem)}.jsonl"
        full_key = self._build_s3_key("clean", relative_key)
        self.logger.debug(f"📥 Retrieving processed JSONL | stem={stem}, key={full_key}")
        data = self.storage_client.get_bytes(self._get_s3_bucket(), full_key)
        if data is None:
            self.logger.debug(f"⚠️ Processed JSONL not found: {full_key}")
            return None

        # Parse JSONL (one JSON object per line)
        records = []
        for line_num, line in enumerate(data.decode("utf-8").splitlines(), 1):
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    self.logger.warning(f"⚠️ Skipping malformed JSON at line {line_num}: {e}")
                    self.logger.debug(f"   Problematic line: {line[:200]}...")  # Log first 200 chars
                    continue
        self.logger.debug(f"✅ Retrieved processed JSONL | records={len(records)}, size={len(data)} bytes")
        return records

    def get_metrics_json(self) -> Optional[List[Dict[str, Any]]]:
        """Retrieve metrics JSON.

        Returns:
            List of metric dictionaries, or None if not found
        """
        relative_key = f"{self._get_processed_prefix()}metrics.json"
        full_key = self._build_s3_key("clean", relative_key)
        self.logger.debug(f"📥 Retrieving metrics JSON | key={full_key}")
        metrics = self.storage_client.get_json(self._get_s3_bucket(), full_key)
        if metrics is None:
            self.logger.debug(f"⚠️ Metrics not found: {full_key}")
            return None
        # Ensure it's a list
        if isinstance(metrics, list):
            self.logger.debug(f"✅ Retrieved metrics | entries={len(metrics)}")
            return metrics
        self.logger.debug(f"✅ Retrieved metrics (converted to list)")
        return [metrics]

    def put_artifact(
        self, artifact_name: str, content: Union[str, bytes], content_type: str = "application/octet-stream"
    ) -> str:
        """Store an artifact (PDF, CSV, etc.).

        Args:
            artifact_name: Artifact name (e.g., "ai_trust_report.pdf")
            content: Artifact content (string or bytes)
            content_type: MIME type

        Returns:
            S3/GCS object key
        """
        # Build artifact key using the artifacts_prefix helper
        prefix = artifacts_prefix(self.workspace_id, self.product_id, self.version)
        full_key = f"{prefix}{safe_filename(artifact_name)}"
        self.logger.debug(f"📤 Building artifact key | prefix={prefix}, full_key={full_key}")

        if isinstance(content, str):
            data = content.encode("utf-8")
        else:
            data = content

        self.logger.debug(f"📤 Storing artifact | name={artifact_name}, key={full_key}, type={content_type}, size={len(data)} bytes")
        success = self.storage_client.put_bytes(
            bucket=self._get_s3_bucket(),
            key=full_key,
            data=data,
            content_type=content_type,
        )
        if not success:
            self.logger.error(f"❌ Failed to store artifact: {full_key}")
            raise RuntimeError(f"Failed to store artifact: {full_key}")
        self.logger.info(f"✅ Stored artifact: {full_key}")
        return full_key

    def get_artifact(self, artifact_name: str) -> Optional[bytes]:
        """Retrieve an artifact.

        Args:
            artifact_name: Artifact name

        Returns:
            Artifact content as bytes, or None if not found
        """
        prefix = artifacts_prefix(self.workspace_id, self.product_id, self.version)
        full_key = f"{prefix}{safe_filename(artifact_name)}"
        self.logger.debug(f"📥 Retrieving artifact | name={artifact_name}, key={full_key}")
        result = self.storage_client.get_bytes(self._get_s3_bucket(), full_key)
        if result:
            self.logger.debug(f"✅ Retrieved artifact | size={len(result)} bytes")
        else:
            self.logger.debug(f"⚠️ Artifact not found: {full_key}")
        return result
