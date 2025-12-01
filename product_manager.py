"""
Qt helper to append products into index.html and keep JSON-LD in sync.
Requires PyQt5 (pip install pyqt5). Run: python product_manager.py
"""

import json
import re
import sys
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import requests

from PyQt5 import QtCore, QtWidgets
try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # Pillow might not be installed
    Image = None
    UnidentifiedImageError = Exception


INDEX_PATH = Path("index.html")
IMAGES_DIR = Path("images")
MAX_WIDTH = 350


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
        "image": product["image"],
    }
    data.setdefault("itemListElement", []).append(item)
    data["numberOfItems"] = len(data["itemListElement"])

    new_schema = json.dumps(data, indent=2)
    return content.replace(schema_str, new_schema, 1)


def add_product(product: dict) -> None:
    product = product.copy()
    product["image"] = cache_image_as_webp(product["image"], product["title"])

    content = load_file(INDEX_PATH)
    content = update_products_js(content, product)
    content = update_json_ld(content, product)
    save_file(INDEX_PATH, content)
    save_file(Path("404.html"), content)
    print(f"Added product: {product['title']}")


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "image"


def fetch_image_bytes(image_url: str, accept_header: str) -> Tuple[bytes, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://xpresszone.github.io/products/",
        "Accept": accept_header,
    }
    try:
        resp = requests.get(image_url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "")
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response else "no-status"
        reason = exc.response.reason if exc.response else ""
        body_snippet = exc.response.text[:300] if exc.response and exc.response.text else ""
        print(f"[image-download] HTTP {status} for {image_url}: {reason}")
        if body_snippet:
            print(f"[image-download] body: {body_snippet}")
        raise
    except requests.RequestException as exc:
        print(f"[image-download] Request error for {image_url}: {exc}")
        raise


def cache_image_as_webp(image_url: str, title: str) -> str:
    if Image is None:
        raise RuntimeError("Pillow is required to convert images to webp. Install with: pip install Pillow")

    IMAGES_DIR.mkdir(exist_ok=True)
    slug = slugify(title)
    dest = IMAGES_DIR / f"{slug}.webp"

    # First try without AVIF to avoid formats Pillow may not decode
    accept_primary = "image/webp,image/jpeg,image/png,image/*;q=0.8,*/*;q=0.5"
    data, content_type = fetch_image_bytes(image_url, accept_primary)

    # If server still returns AVIF, try a secondary request with stricter accept
    if "avif" in content_type.lower() or b"ftypavif" in data[:32]:
        print(f"[image-download] Received AVIF, retrying with jpeg/png preference for {image_url}")
        data, content_type = fetch_image_bytes(image_url, "image/jpeg,image/png,*/*;q=0.5")

    try:
        with Image.open(BytesIO(data)) as img:
            img = img.convert("RGB")
            if img.width > MAX_WIDTH:
                new_height = max(1, int((MAX_WIDTH / float(img.width)) * img.height))
                img = img.resize((MAX_WIDTH, new_height), Image.LANCZOS)
            img.save(dest, "WEBP", quality=85, method=6)
    except UnidentifiedImageError:
        head = data[:80]
        print(f"[image-download] Unidentified image for {image_url}")
        print(f"[image-download] Content-Type: {content_type}")
        print(f"[image-download] Bytes head (len={len(data)}): {head}")
        raise

    return str(dest).replace("\\", "/")


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
