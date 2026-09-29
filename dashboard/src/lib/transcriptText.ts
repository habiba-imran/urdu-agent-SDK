/** Strip TTS delivery markup from stored/live transcript text (all providers). */

const SPELL_WRAP_RE = /<\/?spell\b[^>]*>([\s\S]*?)<\/spell>/gi;
const SSML_TAG_RE =
  /<\/?(?:break|emotion|spell|speed|volume)[^\s>]*(?:\s[^>]*)?\/?>/gi;
const MIST_PAUSE_RE = /<\d{2,4}>/g;
const BRACKET_CUE_RE = /\[[^\[\]]{1,64}\]/g;
const MARKDOWN_RE = /[*_`#]+/g;

export function stripTranscriptMarkup(text: string | null | undefined): string {
  if (!text) {
    return text ?? '';
  }
  let out = text.replace(SPELL_WRAP_RE, '$1');
  out = out.replace(SSML_TAG_RE, '');
  out = out.replace(MIST_PAUSE_RE, '');
  out = out.replace(BRACKET_CUE_RE, '');
  out = out.replace(MARKDOWN_RE, '');
  return out.replace(/[ \t]{2,}/g, ' ').trim();
}
