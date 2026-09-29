import { redirect } from 'next/navigation';

/** Legacy Integration route — Docs replaces it. */
export default function IntegrationRedirect() {
  redirect('/docs/overview');
}
