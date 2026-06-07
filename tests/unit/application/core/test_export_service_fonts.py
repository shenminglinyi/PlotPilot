from dataclasses import dataclass
from pathlib import Path

from application.core.services.export_service import ExportService


@dataclass(frozen=True)
class _FontSettings:
    paths: tuple[Path, ...]

    def cjk_font_paths(self):
        yield from self.paths


class _Pdf:
    def __init__(self):
        self.fonts = []

    def add_font(self, family, style, path, uni):
        self.fonts.append((family, style, path, uni))


def test_export_service_registers_first_existing_cjk_font(tmp_path):
    missing = tmp_path / "missing.ttf"
    existing = tmp_path / "existing.ttf"
    existing.write_bytes(b"font")
    service = ExportService(
        novel_repository=None,
        chapter_repository=None,
        font_settings=_FontSettings((missing, existing)),
    )
    pdf = _Pdf()

    assert service._try_register_cjk_font(pdf) is True
    assert pdf.fonts == [("PlotExportCJK", "", str(existing), True)]


def test_export_service_skips_when_no_cjk_font_exists(tmp_path):
    service = ExportService(
        novel_repository=None,
        chapter_repository=None,
        font_settings=_FontSettings((tmp_path / "missing.ttf",)),
    )

    assert service._try_register_cjk_font(_Pdf()) is False
