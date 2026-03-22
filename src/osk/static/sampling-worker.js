self.addEventListener("message", (event) => {
  const payload = event.data || {};
  if (payload.type !== "compare") {
    return;
  }

  const width = Math.max(1, Number(payload.width || 0));
  const height = Math.max(1, Number(payload.height || 0));
  const threshold = Math.max(0, Number(payload.threshold || 0));
  const pixels = new Uint8ClampedArray(payload.pixels || 0);

  let score = 1;
  if (
    self.__oskPreviousPixels &&
    self.__oskPreviousWidth === width &&
    self.__oskPreviousHeight === height
  ) {
    let totalDiff = 0;
    let samples = 0;
    for (let index = 0; index < pixels.length; index += 16) {
      totalDiff += Math.abs(pixels[index] - self.__oskPreviousPixels[index]);
      totalDiff += Math.abs(pixels[index + 1] - self.__oskPreviousPixels[index + 1]);
      totalDiff += Math.abs(pixels[index + 2] - self.__oskPreviousPixels[index + 2]);
      samples += 3;
    }
    score = samples ? totalDiff / (samples * 255) : 0;
  }

  self.__oskPreviousPixels = new Uint8ClampedArray(pixels);
  self.__oskPreviousWidth = width;
  self.__oskPreviousHeight = height;

  self.postMessage({
    type: "frame_score",
    score,
    changed: score >= threshold,
  });
});
