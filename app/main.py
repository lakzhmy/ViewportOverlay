import sys

from PySide6.QtWidgets import QApplication

from viewport_overlay.screen import set_app_id
from viewport_overlay.window import MainWindow


def main() -> int:
    set_app_id()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
