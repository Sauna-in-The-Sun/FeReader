import sys
import os
import tempfile
import shutil
import posixpath
import configparser
import json

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTextBrowser,
    QFileDialog,
    QToolBar,
    QMessageBox,
    QStatusBar,
    QInputDialog,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QDialog,
    QComboBox,
    QSpinBox,
    QPushButton,
    QHBoxLayout,
    QCheckBox,
)

from PySide6.QtGui import (
    QFont,
    QPixmap,
    QImage,
    QColor,
    QTextCharFormat,
    QFontDatabase,
    QDesktopServices,
    QKeySequence,
    QPainter,
    QTextCursor,
    QAction,
    QActionGroup,
)
from PySide6.QtCore import Qt, QUrl, Signal, QSettings

from ebooklib import epub
import ebooklib
from bs4 import BeautifulSoup
import fitz  

APP_VERSION = "3.0.0"

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

LANG_STRINGS = {
    "en": {
        "menu": "Menu",
        "open": "Open",
        "settings": "Setting",
        "convert": "Convert",
        "exit": "Exit",
        "prev": "Prev",
        "next": "Next",
        "goto": "Go to",
        "one_page": "One Page",
        "all_pages": "All Pages",
        "help": "Help",
        "view_help": "View Help",
        "about": "About FeReader",
        "font": "Font",
        "theme": "Theme",
        "language": "Language",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "language_en": "English (US)",
        "language_th": "ภาษาไทย",
        "settings_title": "Settings",
        "convert_title": "Convert",
        "no_document": "No document loaded.",
        "view": "View",
        "vertical": "Vertical",
        "horizontal": "Horizon",
    },
    "th": {
        "menu": "เมนู",
        "open": "เปิด",
        "settings": "ตั้งค่า",
        "convert": "แปลงเอกสาร",
        "exit": "ออก",
        "prev": "ก่อนหน้า",
        "next": "ถัดไป",
        "goto": "ข้ามหน้า",
        "one_page": "ทีละหน้า",
        "all_pages": "ทุกหน้า",
        "help": "ช่วยเหลือ",
        "view_help": "ดูการช่วยเหลือ",
        "about": "เกี่ยวกับ FeReader",
        "font": "ฟอนต์",
        "theme": "ธีม",
        "language": "ภาษา",
        "theme_light": "โหมดสว่าง",
        "theme_dark": "โหมดมืด",
        "language_en": "English (US)",
        "language_th": "ภาษาไทย",
        "settings_title": "ตั้งค่า",
        "convert_title": "แปลงเอกสาร",
        "no_document": "ยังไม่มีเอกสารถูกเปิด",
        "view": "มุมมอง",
        "vertical": "แนวตั้ง",
        "horizontal": "อ่านแบบซ้ายขวาเหมือนหนังสือ",
    },
}


class PageScrollArea(QScrollArea):
    """Scroll area that can flip pages with mouse wheel."""

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


class SettingsDialog(QDialog):
    def __init__(self, parent, fonts, current_font, current_size, current_theme, current_lang):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(LANG_STRINGS[current_lang]["settings_title"])

        self.font_combo = QComboBox()
        self.font_combo.addItems(fonts)
        if current_font in fonts:
            self.font_combo.setCurrentText(current_font)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 48)
        self.size_spin.setValue(current_size)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(
            [LANG_STRINGS[current_lang]["theme_light"], LANG_STRINGS[current_lang]["theme_dark"]]
        )
        if current_theme.lower() == "dark":
            self.theme_combo.setCurrentIndex(1)
        else:
            self.theme_combo.setCurrentIndex(0)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem(LANG_STRINGS[current_lang]["language_en"], "en")
        self.lang_combo.addItem(LANG_STRINGS[current_lang]["language_th"], "th")
        if current_lang == "th":
            self.lang_combo.setCurrentIndex(1)
        else:
            self.lang_combo.setCurrentIndex(0)

        layout = QVBoxLayout(self)

        font_row = QHBoxLayout()
        font_label = QLabel(LANG_STRINGS[current_lang]["font"] + ":")
        font_row.addWidget(font_label)
        font_row.addWidget(self.font_combo)

        size_row = QHBoxLayout()
        size_label = QLabel("Size:")
        size_row.addWidget(size_label)
        size_row.addWidget(self.size_spin)

        theme_row = QHBoxLayout()
        theme_label = QLabel(LANG_STRINGS[current_lang]["theme"] + ":")
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_combo)

        lang_row = QHBoxLayout()
        lang_label = QLabel(LANG_STRINGS[current_lang]["language"] + ":")
        lang_row.addWidget(lang_label)
        lang_row.addWidget(self.lang_combo)

        layout.addLayout(font_row)
        layout.addLayout(size_row)
        layout.addLayout(theme_row)
        layout.addLayout(lang_row)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def get_values(self):
        theme = "light" if self.theme_combo.currentIndex() == 0 else "dark"
        lang = self.lang_combo.currentData()
        return {
            "font_family": self.font_combo.currentText(),
            "font_size": self.size_spin.value(),
            "theme": theme,
            "language": lang,
        }


class ConvertDialog(QDialog):
    def __init__(self, parent, current_lang):
        super().__init__(parent)
        self.setModal(True)
        self.current_lang = current_lang
        self.setWindowTitle(LANG_STRINGS[current_lang]["convert_title"])

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
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_btn)
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_btn)
        layout.addWidget(self.password_check)
        layout.addWidget(self.password_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.convert_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.input_paths = []
        self.output_path = ""

    def choose_input(self):
        mode = self.mode_combo.currentData()
        if mode == "images_pdf":
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Select images", "", "Images (*.png *.jpg *.jpeg *.bmp)"
            )
            if paths:
                self.input_paths = paths
                self.input_label.setText(f"Input: {len(paths)} image(s) selected")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select text file", "", "Text files (*.txt);;All files (*.*)"
            )
            if path:
                self.input_paths = [path]
                self.input_label.setText(f"Input: {os.path.basename(path)}")

    def choose_output(self):
        mode = self.mode_combo.currentData()
        if mode in ("text_pdf", "images_pdf"):
            path, _ = QFileDialog.getSaveFileName(
                self, "Save PDF", "", "PDF files (*.pdf)"
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save EPUB", "", "EPUB files (*.epub)"
            )
        if path:
            self.output_path = path
            self.output_label.setText(f"Output: {os.path.basename(path)}")

    def perform_convert(self):
        mode = self.mode_combo.currentData()
        if not self.input_paths:
            QMessageBox.warning(self, "Error", "No input selected.")
            return
        if not self.output_path:
            QMessageBox.warning(self, "Error", "No output selected.")
            return

        try:
            if mode == "text_pdf":
                self._convert_text_to_pdf()
            elif mode == "text_epub":
                self._convert_text_to_epub()
            elif mode == "images_pdf":
                self._convert_images_to_pdf()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Conversion failed:\n{e}")
            return

        QMessageBox.information(self, "Success", "Conversion completed.")
        self.accept()

    def _convert_text_to_pdf(self):
        path = self.input_paths[0]
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        doc = fitz.open()
        page = doc.new_page()
        rect = fitz.Rect(50, 50, 550, 800)
        page.insert_textbox(rect, text, fontsize=11, align=0)

        if self.password_check.isChecked() and self.password_edit.text():
            pw = self.password_edit.text()
            doc.save(
                self.output_path,
                encryption=fitz.PDF_ENCRYPT_AES_128,
                owner_pw=pw,
                user_pw=pw,
            )
        else:
            doc.save(self.output_path)

        doc.close()

    def _convert_text_to_epub(self):
        path = self.input_paths[0]
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        book = epub.EpubBook()
        book.set_identifier("fereader-convert")
        book.set_title(os.path.basename(path))
        book.set_language("en")

        chapter = epub.EpubHtml(title="Chapter 1", file_name="chap_1.xhtml", lang="en")
        chapter.content = f"<html><body><pre>{text}</pre></body></html>"
        book.add_item(chapter)

        book.toc = (chapter,)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav", chapter]

        epub.write_epub(self.output_path, book)

    def _convert_images_to_pdf(self):
        doc = fitz.open()
        for img_path in self.input_paths:
            img_doc = fitz.open(img_path)
            rect = img_doc[0].rect
            page = doc.new_page(width=rect.width, height=rect.height)
            page.insert_image(rect, filename=img_path)
            img_doc.close()

        if self.password_check.isChecked() and self.password_edit.text():
            pw = self.password_edit.text()
            doc.save(
                self.output_path,
                encryption=fitz.PDF_ENCRYPT_AES_128,
                owner_pw=pw,
                user_pw=pw,
            )
        else:
            doc.save(self.output_path)
        doc.close()


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class FeReaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.config_path = os.path.join(APP_DIR, "settings.ini")
        self.config = configparser.ConfigParser()
        self._load_or_create_settings()

        self.settings = QSettings("Neofilisoft", "FeReader")  

        self.language = self.config["General"]["language"]
        self.theme = self.config["General"]["theme"]
        self.font_family = self.config["General"]["font_family"]
        self.base_font_size = int(self.config["General"]["font_size"])

        self.current_book_type = None
        self.current_book_path = None
        self.current_book_title = "Untitled"
        self.pages = []
        self.current_index = 0
        self.current_font_size = self.base_font_size
        self.current_zoom = 1.0
        
        self.pdf_doc = None 
        
        self.epub_temp_dir = None
        self.view_mode = "single"
        self.view_orientation = "vertical"
        self._continuous_needs_build = True

        self._load_user_fonts()

        self.setWindowTitle(f"FeReader - PDF & EPUB Viewer Version {APP_VERSION}")
        self.resize(1000, 700)

        self.stack = QStackedWidget()

        self.text_view = QTextBrowser()
        self.text_view.setOpenExternalLinks(True)
        self.text_view.setFont(QFont(self.font_family, self.current_font_size))
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
        self.multi_layout.setContentsMargins(0, 0, 0, 0)
        self.multi_layout.setSpacing(16)

        self.multi_scroll = QScrollArea()
        self.multi_scroll.setWidgetResizable(True)
        self.multi_scroll.setWidget(self.multi_container)

        self.stack.addWidget(self.text_view)
        self.stack.addWidget(self.single_scroll)
        self.stack.addWidget(self.multi_scroll)
        self.setCentralWidget(self.stack)

        self._create_toolbar()
        self._create_statusbar()

        self.apply_theme()
        self.apply_language()
        self._update_view()
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)

        if self.settings.value("window/fullscreen", "false") == "true":
            self.showFullScreen()
        elif self.settings.value("window/maximized", "false") == "true":
            self.showMaximized()

    def closeEvent(self, event):
        # Cleanup temporary files
        self._cleanup_epub_temp()
        
        # Close PDF document if open
        if self.pdf_doc:
            self.pdf_doc.close()
            self.pdf_doc = None

        # Save settings
        self.save_settings()
        
        # Save window state
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/fullscreen", str(self.isFullScreen()).lower())
        self.settings.setValue("window/maximized", str(self.isMaximized()).lower())
    
        event.accept()

    def _load_or_create_settings(self):
        defaults = {
            "theme": "light",
            "font_family": "Segoe UI",
            "font_size": "16",
            "language": "en",
        }
        if os.path.exists(self.config_path):
            try:
                self.config.read(self.config_path, encoding="utf-8")
            except Exception:
                self.config = configparser.ConfigParser()
        if "General" not in self.config:
            self.config["General"] = {}
        general = self.config["General"]
        for key, value in defaults.items():
            general.setdefault(key, value)

        with open(self.config_path, "w", encoding="utf-8") as f:
            self.config.write(f)

    def save_settings(self):
        general = self.config["General"]
        general["theme"] = self.theme
        general["font_family"] = self.font_family
        general["font_size"] = str(self.base_font_size)
        general["language"] = self.language
        with open(self.config_path, "w", encoding="utf-8") as f:
            self.config.write(f)

    def _load_user_fonts(self):
        for name in os.listdir(APP_DIR):
            if name.lower().endswith((".ttf", ".otf")):
                try:
                    QFontDatabase.addApplicationFont(os.path.join(APP_DIR, name))
                except Exception:
                    pass

    def tr(self, key):
        bundle = LANG_STRINGS.get(self.language, LANG_STRINGS["en"])
        return bundle.get(key, key)

    def apply_language(self):
        self.menu_button.setText(self.tr("menu"))
        self.prev_action.setText(self.tr("prev"))
        self.next_action.setText(self.tr("next"))
        self.goto_action.setText(self.tr("goto"))
        self.one_page_action.setText(self.tr("one_page"))
        self.all_pages_action.setText(self.tr("all_pages"))
        self.help_button.setText(self.tr("help"))

        self.menu_button.setToolTip(self.tr("menu"))
        self.help_button.setToolTip(self.tr("help"))

        self.open_action.setText(self.tr("open"))
        self.settings_action.setText(self.tr("settings"))
        self.convert_action.setText(self.tr("convert"))
        self.exit_action.setText(self.tr("exit"))

        self.view_help_action.setText(self.tr("view_help"))
        self.about_action.setText(self.tr("about"))

        self.view_button.setText(self.tr("view"))
        self.view_vertical_action.setText(self.tr("vertical"))
        self.view_horizontal_action.setText(self.tr("horizontal"))

    def apply_theme(self):
        """Apply light/dark theme including toolbar and hide menu indicators."""
        if self.theme == "dark":
            self.setStyleSheet(
                """
            QMainWindow {
                background-color: #202020;
                color: #f0f0f0;
            }
            QTextBrowser {
                background-color: #202020;
                color: #f0f0f0;
            }
            QLabel {
                color: #f0f0f0;
            }

            QToolBar {
                background: #f5f5f5;
                border: none;
                spacing: 6px;
            }

            QToolButton {
                background: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 4px 8px;
                border-radius: 3px;
            }
            QToolButton:hover {
                background: #eaeaea;
            }
            QToolButton:pressed {
                background: #dddddd;
            }
            QToolButton:checked {
                background: #d0d0d0;
                border: 1px solid #aaaaaa;
            }

            QToolButton::menu-indicator {
                image: none;
                width: 0px;
                height: 0px;
            }

            QScrollArea {
                background: #202020;
            }
            QScrollArea QWidget {
                background: #202020;
            }
            """
            )
        else:
            self.setStyleSheet(
                """
            QMainWindow {
                background-color: #ffffff;
                color: #000000;
            }
            QTextBrowser {
                background-color: #ffffff;
                color: #000000;
            }
            QLabel {
                color: #000000;
            }

            QToolBar {
                background: #f2f2f2;
                border: none;
                spacing: 6px;
            }

            QToolButton {
                background: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 4px 8px;
                border-radius: 3px;
            }
            QToolButton:hover {
                background: #eaeaea;
            }
            QToolButton:pressed {
                background: #dddddd;
            }
            QToolButton:checked {
                background: #d0d0d0;
                border: 1px solid #aaaaaa;
            }

            QToolButton::menu-indicator {
                image: none;
                width: 0px;
                height: 0px;
            }

            QScrollArea {
                background: #ffffff;
            }
            QScrollArea QWidget {
                background: #ffffff;
            }
            """
            )

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        from PySide6.QtWidgets import QToolButton, QMenu

        self.menu_button = QToolButton()
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self.menu_menu = QMenu()

        self.open_action = QAction(self.tr("open"), self)
        self.open_action.setShortcut(QKeySequence("Ctrl+O"))
        self.open_action.triggered.connect(self.open_file)

        self.settings_action = QAction(self.tr("settings"), self)
        self.settings_action.setShortcut(QKeySequence("F1"))
        self.settings_action.triggered.connect(self.open_settings_dialog)

        self.convert_action = QAction(self.tr("convert"), self)
        self.convert_action.setShortcut(QKeySequence("F2"))
        self.convert_action.triggered.connect(self.open_convert_dialog)

        self.exit_action = QAction(self.tr("exit"), self)
        self.exit_action.setShortcut(QKeySequence("Alt+F4"))
        self.exit_action.triggered.connect(QApplication.instance().quit)

        self.menu_menu.addAction(self.open_action)
        self.menu_menu.addAction(self.settings_action)
        self.menu_menu.addAction(self.convert_action)
        self.menu_menu.addSeparator()
        self.menu_menu.addAction(self.exit_action)

        self.menu_button.setMenu(self.menu_menu)
        self.menu_button.setText(self.tr("menu"))
        toolbar.addWidget(self.menu_button)

        self.view_button = QToolButton()
        self.view_button.setPopupMode(QToolButton.InstantPopup)
        self.view_menu = QMenu()

        self.view_vertical_action = QAction(self.tr("vertical"), self)
        self.view_vertical_action.setCheckable(True)

        self.view_horizontal_action = QAction(self.tr("horizontal"), self)
        self.view_horizontal_action.setCheckable(True)

        view_orient_group = QActionGroup(self)
        view_orient_group.setExclusive(True)
        view_orient_group.addAction(self.view_vertical_action)
        view_orient_group.addAction(self.view_horizontal_action)

        self.view_vertical_action.setChecked(True)

        self.view_vertical_action.triggered.connect(
            lambda: self.set_view_orientation("vertical")
        )
        self.view_horizontal_action.triggered.connect(
            lambda: self.set_view_orientation("horizontal")
        )

        self.view_menu.addAction(self.view_vertical_action)
        self.view_menu.addAction(self.view_horizontal_action)

        self.view_button.setMenu(self.view_menu)
        self.view_button.setText(self.tr("view"))
        toolbar.addWidget(self.view_button)

        toolbar.addSeparator()

        self.prev_action = QAction(self.tr("prev"), self)
        self.prev_action.triggered.connect(self.go_prev)
        toolbar.addAction(self.prev_action)

        self.next_action = QAction(self.tr("next"), self)
        self.next_action.triggered.connect(self.go_next)
        toolbar.addAction(self.next_action)

        self.goto_action = QAction(self.tr("goto"), self)
        self.goto_action.triggered.connect(self.go_to_page_dialog)
        toolbar.addAction(self.goto_action)

        toolbar.addSeparator()

        zoom_in_action = QAction("🔍+", self)
        zoom_in_action.setStatusTip("Zoom in / increase font size")
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in_action)

        zoom_out_action = QAction("🔍-", self)
        zoom_out_action.setStatusTip("Zoom out / decrease font size")
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out_action)

        self.zoom_label = ClickableLabel("100%")
        self.zoom_label.setMinimumWidth(60)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.clicked.connect(self.zoom_label_clicked)
        toolbar.addWidget(self.zoom_label)

        toolbar.addSeparator()

        self.one_page_action = QAction(self.tr("one_page"), self)
        self.one_page_action.setCheckable(True)
        self.one_page_action.setChecked(True)

        self.all_pages_action = QAction(self.tr("all_pages"), self)
        self.all_pages_action.setCheckable(True)
        self.all_pages_action.setChecked(False)

        view_group = QActionGroup(self)
        view_group.setExclusive(True)
        view_group.addAction(self.one_page_action)
        view_group.addAction(self.all_pages_action)

        self.one_page_action.triggered.connect(lambda: self.set_view_mode("single"))
        self.all_pages_action.triggered.connect(lambda: self.set_view_mode("continuous"))

        toolbar.addAction(self.one_page_action)
        toolbar.addAction(self.all_pages_action)

        toolbar.addSeparator()

        self.help_button = QToolButton()
        self.help_button.setPopupMode(QToolButton.InstantPopup)
        self.help_menu = QMenu()

        self.view_help_action = QAction(self.tr("view_help"), self)
        self.view_help_action.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/neofilisoft/FeReader")
            )
        )
        self.about_action = QAction(self.tr("about"), self)
        self.about_action.triggered.connect(self.show_about)

        self.help_menu.addAction(self.view_help_action)
        self.help_menu.addAction(self.about_action)

        self.help_button.setMenu(self.help_menu)
        self.help_button.setText(self.tr("help"))
        toolbar.addWidget(self.help_button)

    def _create_statusbar(self):
        status = QStatusBar()
        self.setStatusBar(status)
        self._update_statusbar()

    def _update_statusbar(self):
        if self.pages:
            info = f"{self.current_book_title}  |  Page {self.current_index + 1} / {len(self.pages)}"
        else:
            info = self.tr("no_document")
        self.statusBar().showMessage(info)

    def _update_zoom_label(self):
        if not self.pages:
            self.zoom_label.setText("100%")
            return

        if self.current_book_type == "pdf":
            percent = int(self.current_zoom * 100)
        else:
            ratio = self.current_font_size / float(self.base_font_size)
            percent = int(ratio * 100)

        self.zoom_label.setText(f"{percent}%")

    def zoom_label_clicked(self):
        if not self.pages:
            return

        if self.current_book_type == "pdf":
            current_percent = int(self.current_zoom * 100)
        else:
            current_percent = int(
                self.current_font_size / float(self.base_font_size) * 100
            )

        value, ok = QInputDialog.getInt(
            self,
            "Set Zoom",
            "Enter zoom percentage (50 - 300):",
            value=current_percent,
            min=50,
            max=300,
        )

        if not ok:
            return

        if self.current_book_type == "pdf":
            self.current_zoom = value / 100.0
            if self.current_zoom < 0.5:
                self.current_zoom = 0.5
            if self.current_zoom > 3.0:
                self.current_zoom = 3.0
            if self.view_mode == "continuous":
                self._continuous_needs_build = True
        else:
            new_size = int(self.base_font_size * (value / 100.0))
            if new_size < 8:
                new_size = 8
            if new_size > 40:
                new_size = 40
            self.current_font_size = new_size

        self._update_view()

    def open_file(self):
        dialog_filter = (
            "Documents (*.pdf *.epub);;"
            "PDF Files (*.pdf);;"
            "EPUB Files (*.epub);;"
            "All Files (*.*)"
        )

        path, _ = QFileDialog.getOpenFileName(self, "Open document", "", dialog_filter)
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        
        # Close previous PDF if exists
        if self.pdf_doc:
            self.pdf_doc.close()
            self.pdf_doc = None
            
        try:
            if ext == ".pdf":
                self.load_pdf(path)
            elif ext == ".epub":
                self.load_epub(path)
            else:
                QMessageBox.warning(
                    self, "Unsupported file", "Only PDF and EPUB are supported."
                )
                return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")
            return

        self.current_book_path = path
        self.current_book_title = os.path.basename(path)
        self.current_index = 0
        self.load_highlights()
        self._update_view()

    def load_pdf(self, path):
        """Updated to use lazy loading (does not render images to list immediately)."""
        self.current_book_type = "pdf"
        self.current_zoom = 1.0
        self.view_mode = "single"
        self.view_orientation = "vertical"
        self.one_page_action.setChecked(True)
        self.all_pages_action.setChecked(False)
        self.view_vertical_action.setChecked(True)
        self.view_horizontal_action.setChecked(False)
        self._continuous_needs_build = True

        self.pdf_doc = fitz.open(path)

        if getattr(self.pdf_doc, "needs_pass", False):
            password, ok = QInputDialog.getText(
                self,
                "Password Required",
                "This PDF is encrypted.\nEnter password:",
                QLineEdit.Password,
            )
            if not ok or not password:
                QMessageBox.warning(self, "Cancelled", "Cannot open encrypted PDF.")
                self.pdf_doc.close()
                self.pdf_doc = None
                return
            if not self.pdf_doc.authenticate(password):
                QMessageBox.critical(self, "Error", "Incorrect password.")
                self.pdf_doc.close()
                self.pdf_doc = None
                return

        # Instead of rendering all pages, just set the page count
        self.pages = list(range(self.pdf_doc.page_count))

    def _cleanup_epub_temp(self):
        if self.epub_temp_dir and os.path.isdir(self.epub_temp_dir):
            try:
                shutil.rmtree(self.epub_temp_dir, ignore_errors=True)
            except Exception:
                pass
        self.epub_temp_dir = None

    def load_epub(self, path):
        self.current_book_type = "epub"
        self.pages = []
        self.current_font_size = self.base_font_size

        self._cleanup_epub_temp()
        self.epub_temp_dir = tempfile.mkdtemp(prefix="fereader_epub_")

        book = epub.read_epub(path)

        for item in book.get_items():
            content = item.get_content()
            rel_path = item.file_name.replace("/", os.sep)
            out_path = os.path.join(self.epub_temp_dir, rel_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(content)

        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            html_bytes = item.get_content()
            html = html_bytes.decode("utf-8", errors="ignore")

            html_dir = posixpath.dirname(item.file_name)
            soup = BeautifulSoup(html, "html.parser")

            for img_tag in soup.find_all("img"):
                src = img_tag.get("src")
                if not src:
                    continue
                rel = posixpath.normpath(posixpath.join(html_dir, src))
                local_path = os.path.join(
                    self.epub_temp_dir,
                    rel.replace("/", os.sep),
                )
                file_url = QUrl.fromLocalFile(local_path).toString()
                img_tag["src"] = file_url

            clean_html = str(soup)
            self.pages.append(clean_html)

        if not self.pages:
            self.pages.append("<h3>No readable content found.</h3>")

    def _clear_multi_layout(self):
        while self.multi_layout.count():
            item = self.multi_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_page_to_pixmap(self, index):
        """Helper to render a PDF page to QPixmap on demand."""
        if not self.pdf_doc or not (0 <= index < self.pdf_doc.page_count):
            return None
        try:
            page = self.pdf_doc.load_page(index)
            pix = page.get_pixmap(alpha=True)
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format_RGBA8888,
            )
            return QPixmap.fromImage(img.copy())
        except Exception:
            return None

    def _build_continuous_pdf_widgets(self):
        self._clear_multi_layout()
        zoom = self.current_zoom
        if zoom <= 0:
            zoom = 1.0

        if self.view_orientation == "horizontal":
            indices = range(0, len(self.pages), 2)
        else:
            indices = range(len(self.pages))

        for idx in indices:
            if self.view_orientation == "horizontal":
                pix = self._get_spread_pixmap(idx)
            else:
                pix = self._render_page_to_pixmap(idx)

            if pix is None:
                continue

            w = int(pix.width() * zoom)
            h = int(pix.height() * zoom)
            scaled = pix.scaled(
                w,
                h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setPixmap(scaled)
            self.multi_layout.addWidget(lbl)

        self.multi_layout.addStretch(1)
        self._continuous_needs_build = False

    def _get_spread_pixmap(self, left_index):
        """Return a pixmap that combines two pages side by side starting at left_index."""
        if not self.pdf_doc or not (0 <= left_index < self.pdf_doc.page_count):
            return None

        left_pix = self._render_page_to_pixmap(left_index)
        if left_pix is None:
            return None

        right_pix = None
        if left_index + 1 < self.pdf_doc.page_count:
            right_pix = self._render_page_to_pixmap(left_index + 1)

        if right_pix is None:
            return left_pix

        target_height = max(left_pix.height(), right_pix.height())
        left_scaled = left_pix.scaledToHeight(target_height, Qt.SmoothTransformation)
        right_scaled = right_pix.scaledToHeight(target_height, Qt.SmoothTransformation)

        spread = QPixmap(left_scaled.width() + right_scaled.width(), target_height)
        spread.fill(Qt.transparent)
        painter = QPainter(spread)
        painter.drawPixmap(0, 0, left_scaled)
        painter.drawPixmap(left_scaled.width(), 0, right_scaled)
        painter.end()
        return spread

    def _update_view(self):
        if not self.pages:
            self.stack.setCurrentWidget(self.text_view)
            self.text_view.setPlainText(self.tr("no_document"))
            self._update_statusbar()
            self._update_zoom_label()
            return

        if self.current_book_type == "epub":
            self.stack.setCurrentWidget(self.text_view)
            content = self.pages[self.current_index]
            self.text_view.setHtml(content)
            font = QFont(self.font_family, self.current_font_size)
            self.text_view.setFont(font)

        elif self.current_book_type == "pdf":
            if self.view_mode == "single":
                self.stack.setCurrentWidget(self.single_scroll)

                if self.view_orientation == "horizontal":
                    pix = self._get_spread_pixmap(self.current_index)
                else:
                    pix = self._render_page_to_pixmap(self.current_index)

                if pix is not None:
                    zoom = self.current_zoom if self.current_zoom > 0 else 1.0
                    w = int(pix.width() * zoom)
                    h = int(pix.height() * zoom)
                    scaled = pix.scaled(
                        w,
                        h,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    self.single_image_label.setPixmap(scaled)
                    self.single_image_label.adjustSize()
                else:
                    self.single_image_label.clear()
            else:
                self.stack.setCurrentWidget(self.multi_scroll)
                if self._continuous_needs_build:
                    self._build_continuous_pdf_widgets()

        self._update_statusbar()
        self._update_zoom_label()

    def go_prev(self):
        if not self.pages:
            return

        step = 1
        if (
            self.current_book_type == "pdf"
            and self.view_mode == "single"
            and self.view_orientation == "horizontal"
        ):
            step = 2

        new_index = self.current_index - step
        if new_index < 0:
            new_index = 0

        if new_index != self.current_index:
            self.current_index = new_index
            self._update_view()

    def go_next(self):
        if not self.pages:
            return

        if (
            self.current_book_type == "pdf"
            and self.view_mode == "single"
            and self.view_orientation == "horizontal"
        ):
            step = 2
            total = len(self.pages)
            max_index = total - 1
            if total % 2 == 0:
                max_left = max_index - 1
            else:
                max_left = max_index
            new_index = self.current_index + step
            if new_index > max_left:
                new_index = max_left
        else:
            step = 1
            new_index = self.current_index + step
            if new_index >= len(self.pages):
                new_index = len(self.pages) - 1

        if new_index != self.current_index:
            self.current_index = new_index
            self._update_view()

    def go_to_page_dialog(self):
        if not self.pages:
            return
        max_page = len(self.pages)
        current_page_display = self.current_index + 1
        value, ok = QInputDialog.getInt(
            self,
            "Go to page",
            f"Enter page number (1 - {max_page}):",
            value=current_page_display,
            min=1,
            max=max_page,
        )
        if ok:
            self.current_index = value - 1
            if (
                self.current_book_type == "pdf"
                and self.view_orientation == "horizontal"
                and self.view_mode == "single"
                and self.current_index % 2 == 1
            ):
                self.current_index -= 1           
            self.load_highlights()
            self._update_view()

    def toggle_fullscreen(self):
        if self.isFullScreen():         
            self.showNormal()
        else:
            self.showFullScreen()

    def zoom_in(self):
        if not self.pages:
            return
        if self.current_book_type == "pdf":
            self.current_zoom += 0.15
            if self.current_zoom > 3.0:
                self.current_zoom = 3.0
            if self.view_mode == "continuous":
                self._continuous_needs_build = True
        else:
            self.current_font_size += 1
            if self.current_font_size > 40:
                self.current_font_size = 40
        self._update_view()

    def zoom_out(self):
        if not self.pages:
            return
        if self.current_book_type == "pdf":
            self.current_zoom -= 0.15
            if self.current_zoom < 0.5:
                self.current_zoom = 0.5
            if self.view_mode == "continuous":
                self._continuous_needs_build = True
        else:
            self.current_font_size -= 1
            if self.current_font_size < 8:
                self.current_font_size = 8
        self._update_view()

    def set_view_mode(self, mode: str):
        if self.current_book_type != "pdf":
            return
        if mode == "single":
            self.view_mode = "single"
            self.one_page_action.setChecked(True)
            self.all_pages_action.setChecked(False)
        elif mode == "continuous":
            self.view_mode = "continuous"
            self.one_page_action.setChecked(False)
            self.all_pages_action.setChecked(True)
            self._continuous_needs_build = True
        else:
            return
        self._update_view()

    def set_view_orientation(self, mode: str):
        if mode not in ("vertical", "horizontal"):
            return
        self.view_orientation = mode
        self.view_vertical_action.setChecked(mode == "vertical")
        self.view_horizontal_action.setChecked(mode == "horizontal")

        if self.current_book_type == "pdf":
            if (
                self.view_orientation == "horizontal"
                and self.view_mode == "single"
                and self.current_index % 2 == 1
            ):
                self.current_index -= 1
            if self.view_mode == "continuous":
                self._continuous_needs_build = True
            self._update_view()

    def _handle_text_selection(self):
        if self.current_book_type != "epub":
            return
        
        self.text_view.blockSignals(True)
        
        try:
            cursor = self.text_view.textCursor()
            if not cursor or not cursor.hasSelection():
                return
            
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 255, 0, 128))
            cursor.mergeCharFormat(fmt)

            key = f"highlights/{self.current_book_title}/{self.current_index}"
            existing_raw = self.settings.value(key, "[]")
            try:
                highlights = json.loads(existing_raw)
            except Exception:
                highlights = []
            
            highlights.append({"start": cursor.selectionStart(), "end": cursor.selectionEnd()})
            self.settings.setValue(key, json.dumps(highlights))

        except Exception as e:
            print(f"Selection error: {e}")
            
        finally:
            self.text_view.blockSignals(False)

    def add_bookmark(self):
        if not self.pages:
            return
        name, ok = QInputDialog.getText(self, "Add Bookmark", "Bookmark name:")
        if ok and name:
            key = f"bookmarks/{self.current_book_title}/{name}"
            value = {"index": self.current_index, "position": 0}
            if self.current_book_type == "epub" and self.text_view:
                value["position"] = self.text_view.verticalScrollBar().value()
            self.settings.setValue(key, json.dumps(value))
            QMessageBox.information(self, "Bookmark", f"Bookmark '{name}' added.")

    def view_bookmarks(self):
        base = f"bookmarks/{self.current_book_title}/"
        self.settings.beginGroup(f"bookmarks/{self.current_book_title}")
        keys = self.settings.childKeys()
        bookmarks = []
        for k in keys:
            raw = self.settings.value(base + k)
            try:
                v = json.loads(raw)
                page_display = v.get("index", 0) + 1
            except Exception:
                page_display = "?"
            bookmarks.append(f"{k}: Page {page_display}")
        self.settings.endGroup()
        if bookmarks:
            QMessageBox.information(self, "Bookmarks", "\n".join(bookmarks))
        else:
            QMessageBox.information(self, "Bookmarks", "No bookmarks yet.")

    def load_highlights(self):
        if self.current_book_type != "epub":
            return
        key = f"highlights/{self.current_book_title}/{self.current_index}"
        raw = self.settings.value(key, "[]")
        try:
            highlights = json.loads(raw)
        except Exception:
            highlights = []
        for hl in highlights:
            cursor = self.text_view.textCursor()
            cursor.setPosition(hl["start"])
            cursor.setPosition(hl["end"], QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 255, 0, 128))
            cursor.mergeCharFormat(fmt)
            
    # Dialogs / misc
    def open_settings_dialog(self):
        fonts = sorted(set(QFontDatabase().families()))
        dlg = SettingsDialog(
            self,
            fonts,
            self.font_family,
            self.base_font_size,
            self.theme,
            self.language,
        )
        if dlg.exec() == QDialog.Accepted: 
            values = dlg.get_values()
            self.font_family = values["font_family"]
            self.base_font_size = values["font_size"]
            self.current_font_size = self.base_font_size
            self.theme = values["theme"]
            self.language = values["language"]
            self.apply_theme()
            self.apply_language()
            self.save_settings()
            self._update_view()

    def open_convert_dialog(self):
        dlg = ConvertDialog(self, self.language)
        dlg.exec() 

    def show_about(self):
        text = (
            f"<h3>FeReader Version {APP_VERSION}</h3>"
            "PDF & EPUB Viewer with page navigation, zoom, and image support.\n"
            "Powered by Qt6, PyMuPDF, and ebooklib.<br>"
            "Copyright \u00a9 Neofilisoft</p>"
            "<p><b>Technical Stack:</b><br>"
            "- UI Framework: PySide6 (Qt6) <a href='http://pyside.org'>http://pyside.org</a><br>"
            "- PDF Engine: PyMuPDF (fitz)<br>"
            "- EPUB Parser: ebooklib & BeautifulSoup4</p>"
            "<p><b>License Information:</b><br>"
            "This application uses PySide6, which is licensed under"
            "the GNU Lesser General Public License (LGPLv3).<br>"
            "The source code for PySide6 is available at<br>"
            "<a href='https://www.qt.io/terms-conditions-2024-02/'>"
            "https://www.qt.io/terms-conditions-2024-02/</a></p>"
        )
        QMessageBox.about(self, "About FeReader", text)


def main():
    app = QApplication(sys.argv)
    window = FeReaderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()