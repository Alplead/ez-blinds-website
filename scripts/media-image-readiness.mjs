// Scroll lazy images into view before waiting for browser decoding.
// A failed decode is reported through naturalWidth/naturalHeight, not hidden.
export async function inspectMediaImage(locator) {
  await locator.scrollIntoViewIfNeeded();
  return locator.evaluate(async (img) => {
    if (typeof img.decode === 'function') {
      try {
        await img.decode();
      } catch {
        // Preserve the failed-image state for the caller's diagnostics.
      }
    }
    return {
      complete: img.complete,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      alt: img.getAttribute('alt') || '',
      src: img.currentSrc || img.src
    };
  });
}

/**
 * A real-media acceptance run must not pass on unrelated external images,
 * embedded data or ephemeral blob URLs. WordPress attachment URLs may be
 * absolute or relative, but must resolve to the verified staging origin.
 */
export function mediaImageSourceFailure(src, baseUrl) {
  if (typeof src !== 'string' || !src.trim()) return 'image source is missing';
  try {
    const base = new URL(baseUrl);
    const image = new URL(src, base);
    if (!['http:', 'https:'].includes(image.protocol) ||
        image.origin !== base.origin || image.username || image.password) {
      return 'image source must use the verified same-origin HTTP(S) host';
    }
    if (!image.pathname.startsWith('/wp-content/uploads/') || image.pathname.endsWith('/')) {
      return 'image source must be a WordPress uploads attachment';
    }
    if (image.search || image.hash) {
      return 'image source must not include query parameters or fragments';
    }
    return '';
  } catch {
    return 'image source URL is invalid';
  }
}

/**
 * Require a single real hero on product/home pages. Projects may omit a hero,
 * but duplicate hero slots must never conceal a broken second image.
 */
export function heroImageCountFailure(count, required = true) {
  if (!Number.isInteger(count) || count < 0 || count > 1 || (required && count !== 1)) {
    return `expected ${required ? 'exactly one' : 'at most one'} hero image, found ${count}`;
  }
  return '';
}
