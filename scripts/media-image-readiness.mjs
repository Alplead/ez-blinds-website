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
