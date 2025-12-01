"""
Qt helper to append products into index.html and keep JSON-LD in sync.
Requires PyQt5 (pip install pyqt5). Run: python product_manager.py
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtWidgets


INDEX_PATH = Path("index.html")


def load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def update_products_js(content: str, product: dict) -> str:
    """Insert a new product object before the in-file marker comment."""
    marker = "// Add more products here over time"
    if marker not in content:
        raise ValueError("Marker comment for product insertion not found.")

    def esc(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", " ")
            .strip()
        )

    product_block = (
        "    {\n"
        f"      title: '{esc(product['title'])}',\n"
        f"      url: '{esc(product['url'])}',\n"
        f"      image: '{esc(product['image'])}',\n"
        f"      alt: '{esc(product['alt'])}',\n"
        f"      description: '{esc(product['description'])}'\n"
        "    },\n"
    )

    updated = content.replace(marker, product_block + "    " + marker, 1)
    updated = re.sub(r"}\s*(// Add more products here over time)", "},\n    \\1", updated, count=1)
    return updated


def update_json_ld(content: str, product: dict) -> str:
    """Append product to JSON-LD ItemList and update numberOfItems."""
    match = re.search(
        r'<script type="application/ld\+json">\s*(\{[\s\S]*?\})\s*</script>',
        content,
    )
    if not match:
        raise ValueError("JSON-LD block not found.")

    schema_str = match.group(1)
    data = json.loads(schema_str)

    item = {
        "@type": "ListItem",
        "position": len(data.get("itemListElement", [])) + 1,
        "url": product["url"],
        "name": product["title"],
    }
    data.setdefault("itemListElement", []).append(item)
    data["numberOfItems"] = len(data["itemListElement"])

    new_schema = json.dumps(data, indent=2)
    return content.replace(schema_str, new_schema, 1)


def add_product(product: dict) -> None:
    content = load_file(INDEX_PATH)
    content = update_products_js(content, product)
    content = update_json_ld(content, product)
    save_file(INDEX_PATH, content)
    print(f"Added product: {product['title']}")


class ProductForm(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Add Product to index.html")
        layout = QtWidgets.QFormLayout(self)

        self.json_input = QtWidgets.QPlainTextEdit()
        self.json_input.setMinimumWidth(420)
        self.json_input.setPlainText(
            '{\n'
            '  "title": "",\n'
            '  "url": "",\n'
            '  "image": "",\n'
            '  "alt": "",\n'
            '  "description": ""\n'
            '}\n'
        )
        self.json_input.textChanged.connect(self.update_preview)
        layout.addRow("Product JSON *", self.json_input)

        self.preview_labels = {}
        preview_container = QtWidgets.QVBoxLayout()
        for label_text in ["Title", "URL", "Image", "Alt", "Description"]:
            lbl = QtWidgets.QLabel(f"{label_text}: --")
            lbl.setOpenExternalLinks(True)
            lbl.setTextFormat(QtCore.Qt.RichText)
            lbl.setWordWrap(True)
            self.preview_labels[label_text.lower()] = lbl
            preview_container.addWidget(lbl)
        self.preview_status = QtWidgets.QLabel("")
        self.preview_status.setWordWrap(True)
        preview_container.addWidget(self.preview_status)
        layout.addRow("Parsed Preview", preview_container)

        self.status = QtWidgets.QLabel("")
        layout.addRow(self.status)

        add_button = QtWidgets.QPushButton("Add Product")
        add_button.clicked.connect(self.handle_add)
        layout.addRow(add_button)

    def validate(self, product: dict):
        errors = []
        required_fields = ["title", "url", "image", "alt", "description"]
        for key in required_fields:
            if not product.get(key, "").strip():
                errors.append(f"{key} is required.")

        for key in ["url", "image"]:
            value = product.get(key, "")
            if value and not re.match(r"^https?://", value, re.IGNORECASE):
                errors.append(f"{key} must start with http:// or https://")

        return errors

    def set_preview_display(self, product: Optional[dict], message: Optional[str] = None, ok: bool = False):
        def set_label(key: str, value: str, link: bool = False):
            label = self.preview_labels.get(key)
            if not label:
                return
            if link and value:
                label.setText(f"{key.title()}: <a href=\"{value}\">{value}</a>")
            else:
                label.setText(f"{key.title()}: {value or '--'}")

        if product:
            set_label("title", product.get("title", ""))
            set_label("url", product.get("url", ""), link=True)
            set_label("image", product.get("image", ""), link=True)
            set_label("alt", product.get("alt", ""))
            set_label("description", product.get("description", ""))
        else:
            for key in self.preview_labels:
                set_label(key, "--")

        if message:
            color = "#15803d" if ok else "#b91c1c"
            self.preview_status.setStyleSheet(f"color: {color};")
            self.preview_status.setText(message)
        else:
            self.preview_status.setStyleSheet("")
            self.preview_status.setText("")

    def update_preview(self):
        text = self.json_input.toPlainText().strip()
        if not text:
            self.set_preview_display(None, "Awaiting JSON...", ok=False)
            return
        try:
            product = json.loads(text)
        except json.JSONDecodeError as exc:
            self.set_preview_display(None, f"Invalid JSON: {exc}", ok=False)
            return
        if not isinstance(product, dict):
            self.set_preview_display(None, "JSON must be an object with keys.", ok=False)
            return

        product = {k: str(v).strip() for k, v in product.items()}
        errors = self.validate(product)
        self.set_preview_display(
            product,
            "Valid" if not errors else " | ".join(errors),
            ok=not errors,
        )

    def handle_add(self):
        try:
            product = json.loads(self.json_input.toPlainText() or "{}")
        except json.JSONDecodeError as exc:
            self.status.setStyleSheet("color: #b91c1c;")
            self.status.setText(f"Invalid JSON: {exc}")
            return

        errors = self.validate(product if isinstance(product, dict) else {})
        if errors:
            self.status.setStyleSheet("color: #b91c1c;")
            self.status.setText(" | ".join(errors))
            return

        product = {k: str(v).strip() for k, v in product.items()}
        self.set_preview_display(product, "Valid", ok=True)

        try:
            add_product(product)
            self.status.setStyleSheet("color: #15803d;")
            self.status.setText(f"Added: {product['title']}")
            self.json_input.clear()
        except Exception as exc:  # pylint: disable=broad-except
            self.status.setStyleSheet("color: #b91c1c;")
            self.status.setText(f"Error: {exc}")


def main():
    if not INDEX_PATH.exists():
        print("index.html not found next to this script.")
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    form = ProductForm()
    form.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
