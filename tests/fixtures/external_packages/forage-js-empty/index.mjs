// Foraging fixture: a Node package with no viable JSON-scalar callables.

export const CONSTANT = 1;

export function needsThree(a, b, c) {
  return String(a) + String(b) + String(c);
}
