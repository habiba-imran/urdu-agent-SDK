'use client';

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';

type AvatarSheetKey = 'male' | 'neutral' | 'female';

// Each sheet is a grid of pre-supplied illustrated portraits (public/avatars/*.png). cols/rows
// must match the actual grid layout of that image file.
const AVATAR_SHEETS: Record<AvatarSheetKey, { src: string; cols: number; rows: number }> = {
  male: { src: '/avatars/male-sheet.png', cols: 4, rows: 3 },
  neutral: { src: '/avatars/neutral-sheet.png', cols: 3, rows: 2 },
  female: { src: '/avatars/female-sheet.png', cols: 4, rows: 3 },
};

function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function sheetForGender(gender: string): AvatarSheetKey {
  const normalized = gender.toLowerCase();
  if (normalized === 'male') return 'male';
  if (normalized === 'female') return 'female';
  return 'neutral';
}

/**
 * Renders one cell of a pre-supplied illustrated avatar sheet, picked deterministically per
 * voice (via `seed`, e.g. the voice id) so the same voice always gets the same portrait and
 * portraits stay stable across reloads/filter changes.
 */
export function VoiceAvatar({
  name,
  gender = 'unspecified',
  seed,
  size = 48,
  className,
}: {
  name: string;
  gender?: string;
  seed?: string;
  size?: number;
  className?: string;
}) {
  const sheet = AVATAR_SHEETS[sheetForGender(gender)];
  const cellCount = sheet.cols * sheet.rows;

  const index = useMemo(() => hashString(seed ?? name) % cellCount, [seed, name, cellCount]);
  const row = Math.floor(index / sheet.cols);
  const col = index % sheet.cols;
  const bgPosX = sheet.cols > 1 ? (col / (sheet.cols - 1)) * 100 : 0;
  const bgPosY = sheet.rows > 1 ? (row / (sheet.rows - 1)) * 100 : 0;

  return (
    <div
      role="img"
      aria-label={name}
      className={cn('shrink-0 overflow-hidden rounded-full bg-muted', className)}
      style={{
        width: size,
        height: size,
        backgroundImage: `url(${sheet.src})`,
        backgroundSize: `${sheet.cols * 100}% ${sheet.rows * 100}%`,
        backgroundPosition: `${bgPosX}% ${bgPosY}%`,
        backgroundRepeat: 'no-repeat',
      }}
    />
  );
}
