from PyQt5.QtWidgets import QApplication


def centralize(widget):
    widget.move(
        QApplication.desktop().screen().rect().center()
        - widget.rect().center())
