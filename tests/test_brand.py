"""整合品牌圖：HA 2026.3 起讀 custom_components/<domain>/brand/，缺了整合頁就是「icon not available」。"""
import struct
import unittest
from pathlib import Path

BRAND = Path(__file__).resolve().parent.parent / "custom_components" / "taipower_estimate" / "brand"
RGBA = 6  # PNG color type：帶 alpha（透明背景）


def png_header(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} 不是 PNG"
    width, height, _depth, color_type = struct.unpack(">IIBB", data[16:26])
    return width, height, color_type


class BrandImages(unittest.TestCase):
    def test_icon_sizes_and_alpha(self):
        self.assertEqual(png_header(BRAND / "icon.png"), (256, 256, RGBA))
        self.assertEqual(png_header(BRAND / "icon@2x.png"), (512, 512, RGBA))


if __name__ == "__main__":
    unittest.main()
