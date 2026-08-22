// Foraging fixture: an uncooperative Node package with mixed candidates.
//
// Ships no absorption manifest, no spec, and no probe cases. The foraging
// plane must infer the runtime, entry module, and callables. Contains one
// viable unary string transform (`shout`), a second viable one (`whisper`)
// for multi-callable bundle foraging, a selection-only decoy (`brittle`
// that raises on the held-out empty input), a two-argument candidate, and
// non-callable/private noise that introspection must ignore.

export const CONSTANT = 42;

export function shout(text) {
  if (typeof text !== "string") {
    throw new TypeError("shout expects a string");
  }
  return text.toUpperCase() + "!";
}

export function whisper(text) {
  if (typeof text !== "string") {
    throw new TypeError("whisper expects a string");
  }
  return text.toLowerCase();
}

export function brittle(text) {
  if (typeof text !== "string") {
    throw new TypeError("brittle expects a string");
  }
  if (!text) {
    throw new Error("empty input refused");
  }
  return text.trim();
}

export function needsTwo(first, second) {
  return String(first) + String(second);
}

export function _hidden(text) {
  return text;
}
