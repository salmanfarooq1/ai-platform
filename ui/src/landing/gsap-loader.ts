/** Motion stays in a lazy landing-only chunk and is never loaded with reduced motion. */
export function loadMotion() {
  return import('./native-motion')
}
