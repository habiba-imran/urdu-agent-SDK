import { redirect } from 'next/navigation';

/** Legal surface removed from the client console. */
export default function LegalRedirect() {
  redirect('/');
}
