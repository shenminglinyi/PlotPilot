"""Environment-backed export font configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ExportFontEnvironmentSettings:
    """Typed view of export font environment variables."""

    cjk_font_path: str = ""
    windows_dir: str = r"C:\Windows"
    os_name: str = os.name

    @classmethod
    def from_env(cls) -> "ExportFontEnvironmentSettings":
        return cls(
            cjk_font_path=(os.getenv("PLOTPILOT_EXPORT_CJK_FONT", "") or "").strip(),
            windows_dir=os.getenv("WINDIR", r"C:\Windows"),
            os_name=os.name,
        )

    def cjk_font_paths(self) -> Iterator[Path]:
        if self.cjk_font_path:
            yield Path(self.cjk_font_path)
        if self.os_name == "nt":
            fonts = Path(self.windows_dir) / "Fonts"
            for name in (
                "msyh.ttf",
                "simhei.ttf",
                "simsun.ttc",
                "msyh.ttc",
                "simkai.ttf",
            ):
                yield fonts / name
            return
        for path in (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ):
            yield Path(path)
