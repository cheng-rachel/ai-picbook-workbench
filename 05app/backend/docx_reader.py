"""Small dependency-free DOCX reader for paragraphs and tables."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class DocxContent:
    paragraphs: list[str]
    tables: list[list[list[str]]]


def _text(element: ET.Element) -> str:
    parts = [node.text or "" for node in element.iter(f"{W}t")]
    return " ".join("".join(parts).split())


def read_docx(path: Path) -> DocxContent:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{W}body")
    if body is None:
        raise ValueError(f"DOCX has no body: {path}")
    paragraphs: list[str] = []
    tables: list[list[list[str]]] = []
    for child in body:
        if child.tag == f"{W}p":
            value = _text(child)
            if value:
                paragraphs.append(value)
        elif child.tag == f"{W}tbl":
            rows: list[list[str]] = []
            for row in child.findall(f"{W}tr"):
                rows.append([_text(cell) for cell in row.findall(f"{W}tc")])
            tables.append(rows)
    return DocxContent(paragraphs, tables)

