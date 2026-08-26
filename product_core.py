"""Pure product-document updates shared by the GUI and automation."""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit, urlunsplit


PRODUCT_MARKER = "// Add more products here over time"


def _escape_js(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ").strip()


def _product_block(product: dict) -> str:
    return (
        "    {\n"
        f"      title: '{_escape_js(product['title'])}',\n"
        f"      url: '{_escape_js(product['url'])}',\n"
        f"      realUrl: '{_escape_js(product['real_url'])}',\n"
        f"      image: '{_escape_js(product['image'])}',\n"
        f"      alt: '{_escape_js(product['alt'])}',\n"
        f"      description: '{_escape_js(product['description'])}'\n"
        "    },"
    )


def _normalize_real_url(value: str) -> str:
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def update_products_js(content: str, product: dict) -> str:
    """Append a new URL or replace its existing product object."""
    if PRODUCT_MARKER not in content:
        raise ValueError("Marker comment for product insertion not found.")
    new_block = _product_block(product)
    object_pattern = re.compile(r"(?m)^[ \t]{4,}\{\r?\n(?:^[ \t]{6,}.*\r?\n)+?^[ \t]{4,}\},?")
    matching_objects = []
    desired_real_url = _normalize_real_url(product["real_url"])
    for match in object_pattern.finditer(content):
        real_url_match = re.search(r"(?m)^      realUrl:\s*'((?:\\.|[^'])*)',", match.group(0))
        affiliate_match = re.search(r"(?m)^      url:\s*'((?:\\.|[^'])*)',", match.group(0))
        existing_real_url = _normalize_real_url(real_url_match.group(1)) if real_url_match else ""
        existing_affiliate_url = affiliate_match.group(1).replace("\\'", "'") if affiliate_match else ""
        if existing_real_url == desired_real_url or (not existing_real_url and existing_affiliate_url == product["url"]):
            matching_objects.append(match)
    if matching_objects:
        for index, match in reversed(list(enumerate(matching_objects))):
            replacement = new_block if index == 0 else ""
            content = content[:match.start()] + replacement + content[match.end():]
        return content
    marker_line = "    " + PRODUCT_MARKER
    return content.replace(marker_line, new_block + "\n" + marker_line, 1)


def update_json_ld(content: str, product: dict) -> str:
    """Append or replace a JSON-LD item by URL and keep positions stable."""
    match = re.search(
        r'<script type="application/ld\+json">\s*(\{[\s\S]*?\})\s*</script>',
        content,
    )
    if not match:
        raise ValueError("JSON-LD block not found.")
    data = json.loads(match.group(1))
    items = data.setdefault("itemListElement", [])
    item = {
        "@type": "ListItem",
        "position": 0,
        "url": product["url"],
        "sameAs": product["real_url"],
        "name": product["title"],
        "image": product["image"],
    }
    existing_index = next(
        (
            index for index, value in enumerate(items)
            if (value.get("sameAs") or value.get("url")) == product["real_url"]
            or (not value.get("sameAs") and value.get("url") == product["url"])
        ),
        None,
    )
    if existing_index is None:
        items.append(item)
    else:
        items[existing_index] = item
    for position, value in enumerate(items, start=1):
        value["position"] = position
    data["numberOfItems"] = len(items)
    return content.replace(match.group(1), json.dumps(data, indent=2), 1)
