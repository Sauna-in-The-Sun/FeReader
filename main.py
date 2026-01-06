import sys
import os
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextBrowser, QFileDialog, QToolBar,
    QMessageBox, QStatusBar, QInputDialog, QLabel, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget, QLineEdit, QDialog,
    QComboBox, QSpinBox, QPushButton, QHBoxLayout, QCheckBox, QToolButton, QMenu
)
from PySide6.QtGui import (
    QFont, QFontDatabase, QKeySequence, QAction
)
from PySide6.QtCore import Qt, Signal, QSettings

import module
import render

class PageScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_scroll_prev = None
        self.on_scroll_next = None

    def wheelEvent(self, event):
        if self.on_scroll_prev or self.on_scroll_next:
            delta = event.angleDelta().y()
            bar = self.verticalScrollBar()
            at_top = bar.value() == bar.minimum()
            at_bottom = bar.value() == bar.maximum()
            if delta > 0 and at_top and self.on_scroll_prev:
                self.on_scroll_prev()
                return
            if delta < 0 and at_bottom and self.on_scroll_next:
                self.on_scroll_next()
                return
        super().wheelEvent(event)

class ClickableLabel(QLabel):
    clicked = Signal()
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class SettingsDialog(QDialog):
    def __init__(self, parent, fonts, current_font, current_size, current_theme, current_lang):
        super().__init__(parent)
        self.setModal(True)
        strs = module.LANG_STRINGS[current_lang]
        self.setWindowTitle(strs["settings_title"])

        self.font_combo = QComboBox()
        self.font_combo.addItems(fonts)
        if current_font in fonts:
            self.font_combo.setCurrentText(current_font)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 48)
        self.size_spin.setValue(current_size)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems([strs["theme_light"], strs["theme_dark"]])
        self.theme_combo.setCurrentIndex(1 if current_theme.lower() == "dark" else 0)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem(strs["language_en"], "en")
        self.lang_combo.addItem(strs["language_th"], "th")
        self.lang_combo.setCurrentIndex(1 if current_lang == "th" else 0)

        layout = QVBoxLayout(self)
        self._add_row(layout, strs["font"] + ":", self.font_combo)
        self._add_row(layout, "Size:", self.size_spin)
        self._add_row(layout, strs["theme"] + ":", self.theme_combo)
        self._add_row(layout, strs["language"] + ":", self.lang_combo)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK"); cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept); cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch(1); btn_row.addWidget(ok_btn); btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        self.lang_combo_data = self.lang_combo

    def _add_row(self, layout, label_text, widget):
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        row.addWidget(widget)
        layout.addLayout(row)

    def get_values(self):
        theme = "light" if self.theme_combo.currentIndex() == 0 else "dark"
        lang = self.lang_combo.currentData()
        return {"font_family": self.font_combo.currentText(), "font_size": self.size_spin.value(), "theme": theme, "language": lang}

class ConvertDialog(QDialog):
    def __init__(self, parent, current_lang):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(module.LANG_STRINGS[current_lang]["convert_title"])
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Text -> PDF", "text_pdf")
        self.mode_combo.addItem("Text -> EPUB", "text_epub")
        self.mode_combo.addItem("Images -> PDF", "images_pdf")

        self.input_label = QLabel("Input: (none)")
        self.output_label = QLabel("Output: (none)")
        self.input_btn = QPushButton("Browse input")
        self.output_btn = QPushButton("Browse output")
        self.input_btn.clicked.connect(self.choose_input)
        self.output_btn.clicked.connect(self.choose_output)

        self.password_check = QCheckBox("Protect with password (PDF)")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        self.convert_btn = QPushButton("Convert")
        self.cancel_btn = QPushButton("Cancel")
        self.convert_btn.clicked.connect(self.perform_convert)
        self.cancel_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Mode:"))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.input_label); layout.addWidget(self.input_btn)
        layout.addWidget(self.output_label); layout.addWidget(self.output_btn)
        layout.addWidget(self.password_check); layout.addWidget(self.password_edit)
        
        btn_row = QHBoxLayout()
        btn_row.addStretch(1); btn_row.addWidget(self.convert_btn); btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.input_paths = []
        self.output_path = ""

    def choose_input(self):
        mode = self.mode_combo.currentData()
        if mode == "images_pdf":
            paths, _ = QFileDialog.getOpenFileNames(self, "Select images", "", "Images (*.png *.jpg *.jpeg *.bmp)")
            if paths:
                self.input_paths = paths
                self.input_label.setText(f"Input: {len(paths)} image(s)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select text", "", "Text (*.txt);;All (*.*)")
            if path:
                self.input_paths = [path]
                self.input_label.setText(f"Input: {os.path.basename(path)}")

    def choose_output(self):
        mode = self.mode_combo.currentData()
        ext = "EPUB (*.epub)" if "epub" in mode else "PDF (*.pdf)"
        path, _ = QFileDialog.getSaveFileName(self, "Save file", "", ext)
        if path:
            self.output_path = path
            self.output_label.setText(f"Output: {os.path.basename(path)}")

    def perform_convert(self):
        if not self.input_paths or not self.output_path:
            QMessageBox.warning(self, "Error", "Selection incomplete.")
            return
        
        mode = self.mode_combo.currentData()
        pw = self.password_edit.text() if self.password_check.isChecked() else None
        
        try:
            if mode == "text_pdf":
                module.ConverterLogic.text_to_pdf(self.input_paths[0], self.output_path, pw)
            elif mode == "text_epub":
                module.ConverterLogic.text_to_epub(self.input_paths[0], self.output_path)
            elif mode == "images_pdf":
                module.ConverterLogic.images_to_pdf(self.input_paths, self.output_path, pw)
            
            QMessageBox.information(self, "Success", "Conversion completed.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed: {e}")

class FeReaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.cfg_mgr = module.ConfigManager()
        self.settings = QSettings("Neofilisoft", "FeReader")
        
        self.renderer = render.RenderEngine()

        self.language = self.cfg_mgr.get("language")
        self.theme = self.cfg_mgr.get("theme")
        self.font_family = self.cfg_mgr.get("font_family")
        self.base_font_size = int(self.cfg_mgr.get("font_size"))

        self.current_book_title = "Untitled"
        self.current_index = 0
        self.current_font_size = self.base_font_size
        self.current_zoom = 1.0
        self.view_mode = "single"
        self.view_orientation = "vertical"
        self._continuous_needs_build = True

        self._load_user_fonts()
        self.setWindowTitle(f"FeReader - Version {module.APP_VERSION}")
        self.resize(1600, 900)

        # UI Components
        self.stack = QStackedWidget()
        self.text_view = QTextBrowser()
        self.text_view.setOpenExternalLinks(True)
        self.text_view.selectionChanged.connect(self._handle_text_selection)

        self.single_image_label = QLabel()
        self.single_image_label.setAlignment(Qt.AlignCenter)
        self.single_scroll = PageScrollArea()
        self.single_scroll.setWidgetResizable(True)
        self.single_scroll.setWidget(self.single_image_label)
        self.single_scroll.on_scroll_prev = self.go_prev
        self.single_scroll.on_scroll_next = self.go_next

        self.multi_container = QWidget()
        self.multi_layout = QVBoxLayout(self.multi_container)
        self.multi_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        
        self.multi_scroll = QScrollArea()
        self.multi_scroll.setWidgetResizable(True)
        self.multi_scroll.setWidget(self.multi_container)

        self.stack.addWidget(self.text_view)
        self.stack.addWidget(self.single_scroll)
        self.stack.addWidget(self.multi_scroll)
        self.setCentralWidget(self.stack)

        self._create_actions()
        self._create_toolbar()
        self.setStatusBar(QStatusBar())
        self._update_statusbar()

        self.apply_theme()
        self.apply_language()

    def tr(self, key):
        bundle = module.LANG_STRINGS.get(self.language, module.LANG_STRINGS["en"])
        return bundle.get(key, key)

    def closeEvent(self, event):
        self.renderer.cleanup()
        self.save_settings()
        self.settings.setValue("window/geometry", self.saveGeometry())
        event.accept()

    def save_settings(self):
        self.cfg_mgr.set("theme", self.theme)
        self.cfg_mgr.set("font_family", self.font_family)
        self.cfg_mgr.set("font_size", self.base_font_size)
        self.cfg_mgr.set("language", self.language)
        if self.isFullScreen(): mode = "2"
        elif self.isMaximized(): mode = "1"
        else: mode = "0"
        self.cfg_mgr.set("display_mode", mode)
        self.cfg_mgr.save()

    def _load_user_fonts(self):
        for name in os.listdir(module.APP_DIR):
            if name.lower().endswith((".ttf", ".otf")):
                try: QFontDatabase.addApplicationFont(os.path.join(module.APP_DIR, name))
                except: pass

    def apply_language(self):
        self.menu_btn.setText(self.tr("menu"))
        self.prev_action.setText(self.tr("prev"))
        self.next_action.setText(self.tr("next"))
    
    def apply_theme(self):
        bg, fg = ("#202020", "#f0f0f0") if self.theme == "dark" else ("#ffffff", "#000000")
        tb_bg = "#f5f5f5" if self.theme == "dark" else "#f2f2f2"
        self.setStyleSheet(f"""
            QMainWindow, QTextBrowser, QScrollArea {{ background-color: {bg}; color: {fg}; }}
            QLabel {{ color: {fg}; }}
            QToolBar {{ background: {tb_bg}; border: none; spacing: 6px; }}
            QToolButton::menu-indicator {{ image: none; }}
        """)

    def _create_actions(self):
        self.fullscreen_action = QAction("Fullscreen", self)
        self.fullscreen_action.setShortcut(QKeySequence("F11"))
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self.fullscreen_action)

        self.prev_action = QAction(self.tr("prev"), self)
        self.prev_action.triggered.connect(self.go_prev)
        self.next_action = QAction(self.tr("next"), self)
        self.next_action.triggered.connect(self.go_next)

    def _create_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.menu_btn = QToolButton()
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        
        self.main_menu = QMenu(self)  
        self.main_menu.addAction(self.tr("open"), self.open_file, "Ctrl+O")
        self.main_menu.addAction(self.tr("settings"), self.open_settings_dialog, "F1")
        self.main_menu.addAction(self.tr("convert"), self.open_convert_dialog, "F2")
        self.main_menu.addSeparator()
        self.main_menu.addAction(self.tr("exit"), QApplication.instance().quit, "Alt+F4")
        
        self.menu_btn.setMenu(self.main_menu)
        self.menu_btn.setText(self.tr("file"))
        tb.addWidget(self.menu_btn)

        self.view_btn = QToolButton()
        self.view_btn.setPopupMode(QToolButton.InstantPopup)
        
        self.view_menu = QMenu(self) 
        self.v_act = self.view_menu.addAction(self.tr("vertical"), lambda: self.set_view_orientation("vertical"))
        self.h_act = self.view_menu.addAction(self.tr("horizontal"), lambda: self.set_view_orientation("horizontal"))
        self.v_act.setCheckable(True)
        self.h_act.setCheckable(True)
        self.v_act.setChecked(True)
        
        self.view_btn.setMenu(self.view_menu)
        self.view_btn.setText(self.tr("view"))
        tb.addWidget(self.view_btn)

        tb.addSeparator()
        tb.addAction(self.prev_action)
        tb.addAction(self.next_action)
        
        tb.addSeparator()
        tb.addAction("🔍+", self.zoom_in)
        tb.addAction("🔍-", self.zoom_out)
        self.zoom_label = ClickableLabel("100%")
        self.zoom_label.setMinimumWidth(60)
        self.zoom_label.clicked.connect(self.zoom_label_clicked)
        tb.addWidget(self.zoom_label)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "Files (*.pdf *.epub)")
        if not path: return
        
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".pdf":
                self.renderer.load_pdf(path, lambda: QInputDialog.getText(self, "Password", "Enter:", QLineEdit.Password)[0])
                self.current_zoom = self.renderer.get_initial_zoom(self.single_scroll.width()-25, self.single_scroll.height()-25)
            elif ext == ".epub":
                self.renderer.load_epub(path)
                self.current_font_size = self.base_font_size
            else:
                return

            self.current_book_title = os.path.basename(path)
            self.current_index = 0
            self.load_highlights()
            self._update_view()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _update_view(self):
        if not self.renderer.pages:
            self.stack.setCurrentWidget(self.text_view)
            self.text_view.setPlainText("")
            self._update_statusbar()
            return

        if self.renderer.book_type == "epub":
            self.stack.setCurrentWidget(self.text_view)
            self.text_view.setHtml(self.renderer.pages[self.current_index])
            self.text_view.setFont(QFont(self.font_family, self.current_font_size))
        
        elif self.renderer.book_type == "pdf":
            self.stack.setCurrentWidget(self.single_scroll)
            if self.view_orientation == "horizontal":
                pix = self.renderer.get_pdf_spread_pixmap(self.current_index, self.current_zoom)
            else:
                pix = self.renderer.get_pdf_page_pixmap(self.current_index, self.current_zoom)
            
            if pix:
                self.single_image_label.setPixmap(pix)
                self.single_image_label.adjustSize()
        
        self._update_statusbar()
        self._update_zoom_label()

    def go_prev(self):
        if not self.renderer.pages: return
        step = 2 if (self.renderer.book_type == "pdf" and self.view_orientation == "horizontal") else 1
        self.current_index = max(0, self.current_index - step)
        self._update_view()

    def go_next(self):
        if not self.renderer.pages: return
        step = 2 if (self.renderer.book_type == "pdf" and self.view_orientation == "horizontal") else 1
        limit = len(self.renderer.pages) - 1
        if self.renderer.book_type == "pdf" and self.view_orientation == "horizontal" and limit % 2 != 0:
             limit -= 1
        self.current_index = min(limit, self.current_index + step)
        self._update_view()

    def zoom_in(self):
        if self.renderer.book_type == "pdf":
            self.current_zoom = min(5.0, self.current_zoom + 0.1)
        else:
            self.current_font_size = min(60, self.current_font_size + 2)
        self._update_view()

    def zoom_out(self):
        if self.renderer.book_type == "pdf":
            self.current_zoom = max(0.1, self.current_zoom - 0.1)
        else:
            self.current_font_size = max(8, self.current_font_size - 2)
        self._update_view()

    def zoom_label_clicked(self):
        val, ok = QInputDialog.getInt(self, "Zoom", "Percent:", int(self.current_zoom*100), 50, 300)
        if ok:
            if self.renderer.book_type == "pdf": self.current_zoom = val/100.0
            else: self.current_font_size = int(self.base_font_size * (val/100.0))
            self._update_view()

    def set_view_orientation(self, mode):
        self.view_orientation = mode
        self.v_act.setChecked(mode == "vertical")
        self.h_act.setChecked(mode == "horizontal")
        self._update_view()

    def _update_statusbar(self):
        count = len(self.renderer.pages)
        msg = f"{self.current_book_title} | Page {self.current_index + 1}/{count}" if count else self.tr("no_document")
        self.statusBar().showMessage(msg)

    def _update_zoom_label(self):
        if self.renderer.book_type == "pdf":
            self.zoom_label.setText(f"{int(self.current_zoom * 100)}%")
        else:
            self.zoom_label.setText(f"{int(self.current_font_size/self.base_font_size * 100)}%")

    def toggle_fullscreen(self):
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()

    def _handle_text_selection(self):
        pass

    def load_highlights(self):
        pass

    def open_settings_dialog(self):
        fonts = sorted(set(QFontDatabase().families()))
        dlg = SettingsDialog(self, fonts, self.font_family, self.base_font_size, self.theme, self.language)
        if dlg.exec() == QDialog.Accepted:
            v = dlg.get_values()
            self.font_family = v["font_family"]; self.base_font_size = v["font_size"]
            self.theme = v["theme"]; self.language = v["language"]
            self.current_font_size = self.base_font_size
            self.apply_theme(); self.apply_language(); self.save_settings(); self._update_view()

    def open_convert_dialog(self):
        ConvertDialog(self, self.language).exec()

def main():
    app = QApplication(sys.argv)
    window = FeReaderWindow()
    mode = window.cfg_mgr.get("display_mode", "1")
    if mode == "2": window.showFullScreen()
    elif mode == "1": window.showMaximized()
    else: window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
