import {mousePointer2} from './vendor/lucide/mouse-pointer-2.mjs';

// The single place to change the AI pointer's appearance. Bundled locally for MV3/offline use.
export const CURSOR_THEME = Object.freeze({
  icon: mousePointer2,
  size: 30,
  color: '#2563eb',
  pressedColor: '#1d4ed8',
  outline: '#ffffff',
  idleMs: 2400,
});
