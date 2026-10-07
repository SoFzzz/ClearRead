"""Line icons from resources/icons, recoloured to the active theme (design system 1.7)."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from clearread.core.paths import get_resource_path

ICON_SIZE_PX = 20


def load_icon(name: str, color: str) -> QIcon:
    """Render ``resources/icons/<name>.svg`` with ``currentColor`` replaced by ``color``."""
    path = get_resource_path(f"resources/icons/{name}.svg")
    svg = path.read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(ICON_SIZE_PX, ICON_SIZE_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
