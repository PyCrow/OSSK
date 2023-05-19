# Основные цвета
_DEFAULT_BLACK = "#191919"
_BLACK = "#000"
_RED = "#f00"
_ORANGE = "#f90"
_YELLOW = "#ff0"
_GREEN = "#0f0"

# Подсветка элементов
_DIRECT_LIGHT = "#0a0"

_LINE = (
    f"background-color: {_DEFAULT_BLACK};"
    "border-top: 1px solid {top};"
    "border-left: 1px solid #333;"
    "border-right: 1px solid #333;"
    "border-bottom: 1px solid {bottom};"
    "border-radius: 12px;"
    "padding: 5px;")


class STYLE:
    LINE_VALID = _LINE.format(top=_BLACK, bottom=_DIRECT_LIGHT)
    LINE_INVALID = _LINE.format(top=_RED, bottom=_RED)
    SPIN_VALID = _LINE.format(top=_BLACK, bottom=_DIRECT_LIGHT)
    SPIN_WARNING = _LINE.format(top=_ORANGE, bottom=_ORANGE)
