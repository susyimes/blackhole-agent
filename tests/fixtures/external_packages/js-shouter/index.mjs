// Uncooperative fixture package: ships no absorption manifest.
//
// Used by the capability acquisition plane to prove that a non-Python
// package which never heard of the absorption contract can still be staged,
// adapted, and absorbed through a synthesized node adapter.

export function shout(text) {
  if (typeof text !== "string") {
    throw new TypeError("shout expects a string");
  }
  return text.toUpperCase();
}
