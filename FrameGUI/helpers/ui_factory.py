from __future__ import annotations
import logging
import os
from PySide6 import QtWidgets, QtGui, QtCore
from typing import Optional, Dict, Any, Type, Union

class UIFactory:
    """
    Factory for one-line widget creation and configuration.
    """

    @staticmethod
    def create_widget(
        widget_type: Type[QtWidgets.QWidget],
        parent: Optional[QtWidgets.QWidget] = None,
        text: str = "",
        object_name: str = "",
        style_sheet: str = "",
        geometry: Optional[QtCore.QRect] = None,
        layout: Optional[QtWidgets.QLayout] = None,
        visible: bool = True,
        **properties
    ) -> Union[QtWidgets.QWidget, QtWidgets.QLabel, QtWidgets.QPushButton]:
        """
        Generic creator for any QWidget (including labels, layouts, etc if adapted).
        """
        widget = widget_type(text, parent) if widget_type is QtWidgets.QLabel or widget_type is QtWidgets.QPushButton else widget_type(parent)
        
        if object_name:
            widget.setObjectName(object_name)
        
        if style_sheet:
            widget.setStyleSheet(style_sheet)
            
        if geometry:
            widget.setGeometry(geometry)

        if properties:
            for k, v in properties.items():
                if hasattr(widget, f"set{k.capitalize()}"):
                    getattr(widget, f"set{k.capitalize()}")(v)
                elif hasattr(widget, k):
                    setattr(widget, k, v)
        
        # Extended setup for specific attributes common in our app
        if isinstance(widget, QtWidgets.QLabel):
            pass # Text already set in constructor if provided

        if layout:
            # If the widget is a layout itself (unlikely passed to create_widget as type directly usually), 
            # or we want to adding this widget TO a layout?
            # The user request was "wrap the constructor so we just each widget gets the type... and get everything else needed so each creation is exactly 1 line."
            # Usually meant "create widget AND return it"
            pass

        if visible:
            widget.show()
        else:
            widget.hide()

        return widget

    @staticmethod
    def apply_shadow(widget: QtWidgets.QWidget, radius: int, dx: float, dy: float, color: QtGui.QColor) -> None:
        eff = QtWidgets.QGraphicsDropShadowEffect(widget)
        eff.setBlurRadius(radius)
        eff.setOffset(dx, dy)
        eff.setColor(color)
        widget.setGraphicsEffect(eff)

    @staticmethod
    def apply_font(widget: QtWidgets.QWidget, font_name: str, size_px: int, bold: bool = False) -> None:
        f = QtGui.QFont(font_name)
        f.setPixelSize(size_px)
        f.setBold(bold)
        widget.setFont(f)

    @staticmethod
    def layout(
        layout_type: Type[QtWidgets.QLayout],
        parent_widget: Optional[QtWidgets.QWidget] = None,
        margins: Optional[tuple] = None,
        spacing: int = 0,
        alignment: Optional[QtCore.Qt.Alignment] = None
    ) -> QtWidgets.QLayout:
        
        lay = layout_type(parent_widget) if parent_widget else layout_type()
        if margins:
            lay.setContentsMargins(*margins)
        lay.setSpacing(spacing)
        
        if alignment and hasattr(lay, "setAlignment"):
             lay.setAlignment(alignment)
             
        return lay

    @staticmethod
    def load_font(font_path_or_name: str) -> str:
        """
        Tries to load a font from a file path, returning the family name.
        If not a file, assumes it's already a family name.
        """
        if not font_path_or_name:
            return "Arial"
            
        if os.path.exists(font_path_or_name) and os.path.isfile(font_path_or_name):
            try:
                fid = QtGui.QFontDatabase.addApplicationFont(font_path_or_name)
                fams = QtGui.QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    return fams[0]
            except Exception:
                logging.exception("Failed to load font '%s'", font_path_or_name)
        
        return font_path_or_name
