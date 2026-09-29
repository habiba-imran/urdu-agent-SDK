'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** Legacy `/agents/[id]` full-page editor — details now live in the Agents drawer (read-only). */
export default function AgentDetailRedirectPage() {
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
