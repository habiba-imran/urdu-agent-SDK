'use client';

import { useEffect } from 'react';

let lockCount = 0;
let savedScrollY = 0;

function applyLock(): void {
  if (lockCount === 0) {
    savedScrollY = window.scrollY;
    const body = document.body;
    body.style.position = 'fixed';
    body.style.top = `-${savedScrollY}px`;
    body.style.left = '0';
    body.style.right = '0';
    body.style.width = '100%';
  }
  lockCount += 1;
}

function releaseLock(): void {
  lockCount = Math.max(0, lockCount - 1);
  if (lockCount === 0) {
    const body = document.body;
    body.style.position = '';
    body.style.top = '';
    body.style.left = '';
    body.style.right = '';
    body.style.width = '';
    window.scrollTo(0, savedScrollY);
  }
}

/**
 * Locks page scroll while `locked` is true. Uses the position:fixed trick rather than
 * `overflow:hidden` so it's reliable on iOS Safari. Ref-counted at module scope so two
 * lock-holders (e.g. a modal and a drawer) can overlap without one's unlock clobbering the
 * other's saved scroll position.
 */
export function useScrollLock(locked: boolean): void {
  useEffect(() => {
    if (!locked) return;
    applyLock();
    return releaseLock;
  }, [locked]);
}
