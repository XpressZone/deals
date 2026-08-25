"""Pure product-document updates shared by the GUI and automation."""

from __future__ import annotations

import json
import re


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


def update_products_js(content: str, product: dict) -> str:
    """Append a new URL or replace its existing product object."""
    if PRODUCT_MARKER not in content:
        raise ValueError("Marker comment for product insertion not found.")
    new_block = _product_block(product)
    object_pattern = re.compile(r"(?ms)^    \{\n(?:^      .*\n)+?^    \},?")
    for match in object_pattern.finditer(content):
        real_url_match = re.search(r"(?m)^      realUrl:\s*'((?:\\.|[^'])*)',", match.group(0))
        affiliate_match = re.search(r"(?m)^      url:\s*'((?:\\.|[^'])*)',", match.group(0))
        existing_key = real_url_match or affiliate_match
        desired_key = product["real_url"] if real_url_match else product["url"]
        if existing_key and existing_key.group(1).replace("\\'", "'") == desired_key:
            return content[:match.start()] + new_block + content[match.end():]
    return content.replace(PRODUCT_MARKER, new_block + "\n    " + PRODUCT_MARKER, 1)


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
