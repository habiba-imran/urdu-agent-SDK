'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** Legacy `/telephony` page — phone numbers now show on Agents (read-only). */
export default function TelephonyRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/agents');
  }, [router]);

  return (
    <div className="flex min-h-[40vh] items-center justify-center text-[15px] text-text-muted">
      Opening agents…
    </div>
  );
}
