import unittest

from product_core import update_json_ld, update_products_js


PRODUCT = {
    "title": "Updated product",
    "url": "https://s.click.aliexpress.com/e/_same",
    "real_url": "https://www.aliexpress.com/item/100500.html",
    "image": "images/updated.webp",
    "alt": "Updated alt",
    "description": "Updated description",
}


class ProductManagerTests(unittest.TestCase):
    def test_updates_existing_javascript_product_by_url_without_duplicate(self):
        content = """const products = [
    {
      title: 'Old product',
      url: 'https://s.click.aliexpress.com/e/_same',
      realUrl: 'https://www.aliexpress.com/item/100500.html',
      image: 'images/old.webp',
      alt: 'Old alt',
      description: 'Old description'
    },
    // Add more products here over time
];"""

        updated = update_products_js(content, PRODUCT)

        self.assertEqual(updated.count(PRODUCT["real_url"]), 1)
        self.assertIn("title: 'Updated product'", updated)
        self.assertNotIn("title: 'Old product'", updated)

    def test_collapses_indented_duplicate_cards_by_parameter_free_real_url(self):
        content = """const products = [
        {
      title: 'First duplicate',
      url: 'https://s.click.aliexpress.com/e/_old',
      realUrl: 'https://www.aliexpress.com/item/100500.html?spm=old',
      image: 'images/first.webp',
      alt: 'First',
      description: 'First'
    },
        {
      title: 'Second duplicate',
      url: 'https://s.click.aliexpress.com/e/_new',
      realUrl: 'https://www.aliexpress.com/item/100500.html',
      image: 'images/second.webp',
      alt: 'Second',
      description: 'Second'
    },
    // Add more products here over time
];"""

        updated = update_products_js(content, PRODUCT)

        self.assertEqual(updated.count("item/100500.html"), 1)
        self.assertIn("title: 'Updated product'", updated)
        self.assertNotIn("duplicate", updated)

    def test_updates_existing_json_ld_item_and_keeps_positions(self):
        content = """<script type="application/ld+json">
{"numberOfItems": 2, "itemListElement": [
  {"@type": "ListItem", "position": 1, "url": "https://example.test/first", "name": "First", "image": "first.jpg"},
  {"@type": "ListItem", "position": 2, "url": "https://s.click.aliexpress.com/e/_same", "name": "Old", "image": "old.jpg"}
]}
</script>"""

        updated = update_json_ld(content, PRODUCT)

        self.assertEqual(updated.count(PRODUCT["url"]), 1)
        self.assertIn('"name": "Updated product"', updated)
        self.assertIn('"numberOfItems": 2', updated)
        self.assertIn('"position": 2', updated)


if __name__ == "__main__":
    unittest.main()
