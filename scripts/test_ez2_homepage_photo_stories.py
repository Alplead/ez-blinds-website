#!/usr/bin/env python3
"""Architectural regression for the Owner-approved homepage, photo-led not photo-wall."""
from pathlib import Path
import re
root = Path(__file__).resolve().parents[1]
home = (root / 'wp-content/themes/ezb-theme/templates/front-page.html').read_text()
pattern = (root / 'wp-content/themes/ezb-theme/patterns/core-solutions.php').read_text()
css = (root / 'wp-content/themes/ezb-theme/assets/css/editorial.css').read_text()
checks = 0

def must(test, label):
    global checks
    if not test:
        raise AssertionError(label)
    checks += 1

order = [
    'ezb_editorial_hero', 'ezb-theme/core-solutions',
    'ezb_editorial_interlude photo="flyscreen"', 'ezb-theme/why-ez',
    'ezb-theme/projects-proof', 'ezb-theme/how-it-works',
    'ezb_editorial_interlude photo="roller"', 'ezb-theme/decision-help',
    'ezb-theme/service-area', 'ezb_measure_quote_cta',
]
offset = 0
for item in order:
    index = home.find(item, offset)
    must(index >= offset, f'Homepage approved sequence changed: {item}')
    offset = index + len(item)
must(home.count('ezb-theme/core-solutions') == 1, 'Product section duplicated')
must('ez2-photo-gallery' not in home, 'Photo catalogue inserted into homepage')

products = {
    'Roller Blinds': ('roller-blinds', 'roller-hero'),
    'Sheer Curtains': ('sheer-curtains', 'sheer-hero'),
    'Plantation Shutters': ('plantation-shutters', 'shutters-hero'),
    'Retractable Flyscreens': ('retractable-flyscreens', 'rfs-hero'),
}
for label, (slug, slot) in products.items():
    must(f'href="/{slug}/"' in pattern, f'{label} original product link lost')
    must(pattern.count(f'[ezb_media_slot slot="{slot}"]') == 1,
         f'{label} missing or duplicate curated photo slot')
    must(f'<h3 class="wp-block-heading"><a href="/{slug}/">{label}</a></h3>' in pattern,
         f'{label} heading/text hierarchy lost')
must('href="/motorised-blinds/"' in pattern, 'Motorised Blinds link lost')
must('ezb-feature-card__image--illustrative' in pattern,
     'Motorised Blinds must not be misrepresented by another product photo')
must('href="/products/"' in pattern, 'Original compare-all-products path lost')
must('Core solutions' in pattern, 'Original section title lost')
must('Start with the result you want' in pattern, 'Original advice lost')
must(pattern.count('"tagName":"article"') == 5, 'Five semantic product articles required')
must(pattern.count('<!-- wp:group') == pattern.count('<!-- /wp:group -->'),
     'Product pattern block boundaries unbalanced')
must(pattern.count('<!-- wp:shortcode -->') == 4, 'Photo count must be curated rather than full gallery')
must('ez2-photo-gallery' not in pattern, 'Private photo wall incorrectly embedded')
must('images.unsplash.com' not in pattern, 'Stock image inserted')
must('https://drive.google' not in pattern, 'Private Drive photo link exposed')
for keyword in ['.ezb-feature-card__text', '.ezb-feature-card__image img',
                '.ezb-feature-card--reverse', '@media (max-width: 780px)',
                '@media (prefers-reduced-motion: reduce)']:
    must(keyword in css, f'Editorial visual/responsive rule missing: {keyword}')
print(f'EZ2_HOMEPAGE_PHOTO_STORIES_PASS cases={checks}')
