"""Fill index.html's SUPABASE_URL/ANON_KEY placeholders from .env.local, writing a local-only
index.local.html (gitignored) for testing. The anon key is Supabase's PUBLIC key (safe in client
code by RLS design) but kept out of the committed template so it stays environment-agnostic.

Run: python voice-picker/render_config.py
"""

from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
env = dotenv_values(ROOT / ".env.local")

template = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
rendered = template.replace("__SUPABASE_URL__", env["SUPABASE_URL"]).replace(
    "__SUPABASE_ANON_KEY__", env["SUPABASE_ANON_KEY"]
)
out = Path(__file__).parent / "index.local.html"
out.write_text(rendered, encoding="utf-8")
print(f"wrote {out}")
