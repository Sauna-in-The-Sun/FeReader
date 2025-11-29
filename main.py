import sys
import os
import tempfile
import shutil
import posixpath

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QTextBrowser,
    QFileDialog,
    QToolBar,
    QAction,
    QActionGroup,
    QMessageBox,
    QStatusBar,
    QInputDialog,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtGui import QFont, QPixmap, QImage
from PyQt5.QtCore import Qt, QUrl

from PyPDF2 import PdfReader  # still available if you want text-only later
from ebooklib import epub
import ebooklib  # for ITEM_DOCUMENT
from bs4 import BeautifulSoup
import fitz  # PyMuPDF


class PageScrollArea(QScrollArea):
    """
    QScrollArea that can flip pages with mouse wheel when the
    scroll bar is already at the top or bottom.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_scroll_prev = None  # callback for previous page
        self.on_scroll_next = None  # callback for next page

    def wheelEvent(self, event):
        # Use wheel to flip page only if callbacks are set
        if self.on_scroll_prev or self.on_scroll_next:
            delta = event.angleDelta().y()
            bar = self.verticalScrollBar()
            at_top = bar.value() == bar.minimum()
            at_bottom = bar.value() == bar.maximum()

            if delta > 0 and at_top and self.on_scroll_prev:
                # Scroll up at top -> previous page
                self.on_scroll_prev()
                return
            elif delta < 0 and at_bottom and self.on_scroll_next:
                # Scroll down at bottom -> next page
                self.on_scroll_next()
                return

        # Default scrolling behavior
        super().wheelEvent(event)


class FeReaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- Reader state ---
        self.current_book_type = None  # "pdf" or "epub"
        self.current_book_path = None
        self.current_book_title = "Untitled"

        # Generic page index list; for epub: list of html strings,
        # for pdf: dummy indexes (0..N-1)
        self.pages = []
        self.current_index = 0

        # Display state
        self.base_font_size = 12
        self.current_font_size = self.base_font_size  # EPUB/text mode
        self.current_zoom = 1.0                       # PDF zoom factor

        # PDF rendering cache
        self.pdf_images = []  # list[QImage]

        # EPUB temp directory for extracted files (images, html, etc.)
        self.epub_temp_dir = None

        # PDF view mode: "single" (one page) or "continuous" (all pages)
        self.view_mode = "single"
        self._continuous_needs_build = True

        # --- UI setup ---
        self.setWindowTitle("FeReader - PDF & EPUB Viewer")
        self.resize(1000, 700)

        # Central stacked widget: 0 = EPUB, 1 = PDF single, 2 = PDF continuous
        self.stack = QStackedWidget()

        # Text / HTML view (EPUB)
        self.text_view = QTextBrowser()
        self.text_view.setOpenExternalLinks(True)
        self.text_view.setFont(QFont("Segoe UI", self.current_font_size))

        # PDF single-page view
        self.single_image_label = QLabel()
        self.single_image_label.setAlignment(Qt.AlignCenter)

        self.single_scroll = PageScrollArea()
        self.single_scroll.setWidgetResizable(True)
        self.single_scroll.setWidget(self.single_image_label)
        self.single_scroll.on_scroll_prev = self.go_prev
        self.single_scroll.on_scroll_next = self.go_next

        # PDF continuous (all pages stacked vertically)
        self.multi_container = QWidget()
        self.multi_layout = QVBoxLayout(self.multi_container)
        self.multi_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.multi_layout.setContentsMargins(0, 0, 0, 0)
        self.multi_layout.setSpacing(16)

        self.multi_scroll = QScrollArea()
        self.multi_scroll.setWidgetResizable(True)
        self.multi_scroll.setWidget(self.multi_container)

        self.stack.addWidget(self.text_view)       # index 0
        self.stack.addWidget(self.single_scroll)   # index 1
        self.stack.addWidget(self.multi_scroll)    # index 2

        self.setCentralWidget(self.stack)

        self._create_toolbar()
        self._create_statusbar()

        self._update_view()

    # ----------------- UI creation -----------------

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Open file
        open_action = QAction("Open", self)
        open_action.setStatusTip("Open PDF or EPUB file")
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)

        toolbar.addSeparator()

        # Previous page
        prev_action = QAction("Prev", self)
        prev_action.setStatusTip("Previous page")
        prev_action.triggered.connect(self.go_prev)
        toolbar.addAction(prev_action)

        # Next page
        next_action = QAction("Next", self)
        next_action.setStatusTip("Next page")
        next_action.triggered.connect(self.go_next)
        toolbar.addAction(next_action)

        # Go to page
        goto_action = QAction("Go to...", self)
        goto_action.setStatusTip("Go to page number")
        goto_action.triggered.connect(self.go_to_page_dialog)
        toolbar.addAction(goto_action)

        toolbar.addSeparator()

        # Zoom in (magnifier icon style)
        zoom_in_action = QAction("🔍+", self)
        zoom_in_action.setStatusTip("Zoom in / increase font size")
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in_action)

        # Zoom out
        zoom_out_action = QAction("🔍-", self)
        zoom_out_action.setStatusTip("Zoom out / decrease font size")
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out_action)

        # Zoom percent label
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(60)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        toolbar.addWidget(self.zoom_label)

        toolbar.addSeparator()

        # View mode: One Page vs All Pages
        self.one_page_action = QAction("One Page", self)
        self.one_page_action.setCheckable(True)
        self.one_page_action.setChecked(True)
        self.one_page_action.setStatusTip("Show one page at a time (page flip)")

        self.all_pages_action = QAction("All Pages", self)
        self.all_pages_action.setCheckable(True)
        self.all_pages_action.setChecked(False)
        self.all_pages_action.setStatusTip("Show all pages vertically")

        view_group = QActionGroup(self)
        view_group.setExclusive(True)
        view_group.addAction(self.one_page_action)
        view_group.addAction(self.all_pages_action)

        self.one_page_action.triggered.connect(lambda: self.set_view_mode("single"))
        self.all_pages_action.triggered.connect(lambda: self.set_view_mode("continuous"))

        toolbar.addAction(self.one_page_action)
        toolbar.addAction(self.all_pages_action)

        toolbar.addSeparator()

        # About
        about_action = QAction("About", self)
        about_action.setStatusTip("About FeReader")
        about_action.triggered.connect(self.show_about)
        toolbar.addAction(about_action)

    def _create_statusbar(self):
        status = QStatusBar()
        self.setStatusBar(status)
        self._update_statusbar()

    def _update_statusbar(self):
        if self.pages:
            info = f"{self.current_book_title}  |  Page {self.current_index + 1} / {len(self.pages)}"
        else:
            info = "No document loaded"
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

    # ----------------- File handling -----------------

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

        try:
            if ext == ".pdf":
                self.load_pdf(path)
            elif ext == ".epub":
                self.load_epub(path)
            else:
                QMessageBox.warning(self, "Unsupported file", "Only PDF and EPUB are supported.")
                return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")
            return

        self.current_book_path = path
        self.current_book_title = os.path.basename(path)
        self.current_index = 0
        self._update_view()

    # -------- PDF (image-based rendering with PyMuPDF) --------

    def load_pdf(self, path):
        self.current_book_type = "pdf"
        self.pages = []
        self.pdf_images = []
        self.current_zoom = 1.0
        self.view_mode = "single"
        self.one_page_action.setChecked(True)
        self.all_pages_action.setChecked(False)
        self._continuous_needs_build = True

        doc = fitz.open(path)
        for page in doc:
            pix = page.get_pixmap(alpha=True)
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format_RGBA8888,
            )
            img = img.copy()
            self.pdf_images.append(img)
            self.pages.append(len(self.pages))
        doc.close()

    # -------- EPUB (HTML + inline images) --------

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

        # Extract all items (documents, images, css etc.) to temp folder
        for item in book.get_items():
            content = item.get_content()
            rel_path = item.file_name.replace("/", os.sep)
            out_path = os.path.join(self.epub_temp_dir, rel_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(content)

        # Build HTML pages with fixed <img src="file://..."> so images load correctly
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

    # ----------------- PDF continuous view helpers -----------------

    def _clear_multi_layout(self):
        while self.multi_layout.count():
            item = self.multi_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_continuous_pdf_widgets(self):
        self._clear_multi_layout()

        zoom = self.current_zoom
        if zoom <= 0:
            zoom = 1.0

        for img in self.pdf_images:
            w = int(img.width() * zoom)
            h = int(img.height() * zoom)
            scaled = img.scaled(
                w,
                h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setPixmap(QPixmap.fromImage(scaled))
            self.multi_layout.addWidget(lbl)

        self.multi_layout.addStretch(1)
        self._continuous_needs_build = False

    # ----------------- Navigation & rendering -----------------

    def _update_view(self):
        if not self.pages:
            self.stack.setCurrentWidget(self.text_view)
            self.text_view.setPlainText("No document loaded.")
            self._update_statusbar()
            self._update_zoom_label()
            return

        if self.current_book_type == "epub":
            self.stack.setCurrentWidget(self.text_view)
            content = self.pages[self.current_index]
            self.text_view.setHtml(content)

            font = self.text_view.font()
            font.setPointSize(self.current_font_size)
            self.text_view.setFont(font)

        elif self.current_book_type == "pdf":
            if self.view_mode == "single":
                self.stack.setCurrentWidget(self.single_scroll)

                if 0 <= self.current_index < len(self.pdf_images):
                    base_img = self.pdf_images[self.current_index]
                    zoom = self.current_zoom if self.current_zoom > 0 else 1.0
                    w = int(base_img.width() * zoom)
                    h = int(base_img.height() * zoom)
                    scaled = base_img.scaled(
                        w,
                        h,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    pix = QPixmap.fromImage(scaled)
                    self.single_image_label.setPixmap(pix)
                    self.single_image_label.adjustSize()
                else:
                    self.single_image_label.clear()
            else:
                # Continuous / all pages
                self.stack.setCurrentWidget(self.multi_scroll)
                if self._continuous_needs_build:
                    self._build_continuous_pdf_widgets()

        self._update_statusbar()
        self._update_zoom_label()

    def go_prev(self):
        if not self.pages:
            return
        if self.current_index > 0:
            self.current_index -= 1
            self._update_view()

    def go_next(self):
        if not self.pages:
            return
        if self.current_index < len(self.pages) - 1:
            self.current_index += 1
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
            self._update_view()

    # ----------------- Zoom -----------------

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

    # ----------------- View mode -----------------

    def set_view_mode(self, mode: str):
        if self.current_book_type != "pdf":
            # View mode only affects PDF; ignore for EPUB
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

    # ----------------- Misc -----------------

    def show_about(self):
        QMessageBox.information(
            self,
            "About FeReader",
            "FeReader\nPDF & EPUB Viewer with page navigation, zoom, and image support.\n"
            "Powered by PyQt5, PyMuPDF, and ebooklib.",
        )

    def closeEvent(self, event):
        self._cleanup_epub_temp()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = FeReaderWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
