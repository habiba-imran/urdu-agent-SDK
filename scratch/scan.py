import os
import json
import re
from datetime import datetime, timezone
import glob

SESSION_ID = "CCGEN-20260805-1509"
PROJECT_ROOT = r"c:\Users\habib\Desktop\SDK\sdk-agent"

EXCLUDED_DIRS = {
    "node_modules", ".git", ".next", "dist", "build", ".nuxt", "__pycache__",
    ".cache", ".parcel-cache", "coverage", ".turbo", ".vercel", ".netlify",
    "out", "storybook-static", ".expo", ".svelte-kit", ".output", "tmp",
    "temp", "vendor", "codebase-context", ".codebase-context-system", ".venv"
}

EXCLUDED_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "Cargo.lock", "poetry.lock", "Pipfile.lock", "composer.lock", "Gemfile.lock"
}

BINARY_EXTS = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif", ".bmp", ".tiff", ".raw",
    # Fonts
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    # Media
    ".mp4", ".mp3", ".wav", ".avi", ".mov", ".webm", ".ogg", ".flac",
    # Archives
    ".zip", ".tar", ".gz", ".rar", ".7z", ".tar.gz", ".tgz",
    # Executables
    ".exe", ".dll", ".so", ".dylib", ".bin", ".app",
    # DB files
    ".db", ".sqlite", ".sqlite3",
    # Other
    ".pdf", ".psd", ".ai", ".sketch", ".fig"
}

def is_excluded_file(filename):
    if filename in EXCLUDED_FILES:
        return True
    if filename.endswith(".min.js") or filename.endswith(".min.css") or filename.endswith(".map") or \
       filename.endswith(".chunk.js") or filename.endswith(".bundle.js") or \
       filename.endswith(".generated.ts") or filename.endswith(".generated.js"):
        return True
    return False

def get_category(filename, is_binary):
    if is_binary:
        return "binary"
    ext = os.path.splitext(filename)[1].lower()
    
    if ext in {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".dart", ".php", ".rb", ".java", ".kt", ".cs", ".c", ".cpp", ".h", ".hpp"}:
        if "test" in filename.lower() or "spec" in filename.lower() or filename.startswith("test_"):
            return "test"
        if filename in {"next.config.js", "vite.config.ts", "tailwind.config.ts", "tsconfig.json", "webpack.config.js", "package.json", "requirements.txt", "pytest.ini"}:
            return "config"
        return "code"
    if ext in {".json", ".yaml", ".yml", ".toml", ".ini", ".xml"}:
        return "config"
    if ext in {".css", ".scss", ".sass", ".less"}:
        return "style"
    if ext in {".html", ".htm", ".xml", ".svg"}:
        return "markup"
    if ext == ".env" or filename.startswith(".env"):
        return "env"
    if ext in {".md", ".mdx", ".txt"}:
        return "doc"
    return "other"

def determine_critical_reason(filepath, import_count, content):
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    content_str = content if content else ""
    
    # 1. Imported/required by 5 or more other files in the project
    if import_count is not None and import_count >= 5:
        return f"Imported by {import_count} other files"
    
    # 2. Defines the application entry point (layout.tsx, App.tsx, main.py, server.js, index.ts at root, etc.)
    if filename in {"layout.tsx", "App.tsx", "main.py", "server.js", "index.ts", "index.js", "main.ts", "app.py"}:
        return "Defines the application entry point"
    
    # 3. Initializes or exports the database client/connection
    if content_str and ("createClient(" in content_str or "supabase" in content_str.lower() or "psycopg" in content_str.lower() or "sqlalchemy" in content_str.lower() or "connect(" in content_str) and ("db" in filename.lower() or "database" in filename.lower() or "supabase" in filename.lower() or "client" in filename.lower()):
        return "Initializes or exports the database client/connection"
    
    # 4. Contains authentication logic (sign-in, session management, JWT handling)
    if content_str and ("jwt" in content_str.lower() or "auth" in content_str.lower() or "sign-in" in content_str.lower() or "login" in content_str.lower() or "session" in content_str.lower()) and ("auth" in filename.lower() or "jwt" in filename.lower() or "session" in filename.lower()):
        return "Contains authentication logic"
    
    # 5. Defines global state, context providers, or the primary store
    if content_str and ("createContext" in content_str or "Provider" in content_str or "zustand" in content_str or "redux" in content_str) and ("state" in filename.lower() or "store" in filename.lower() or "context" in filename.lower() or "provider" in filename.lower()):
        return "Defines global state, context providers, or the primary store"
    
    # 6. Defines the primary routing configuration
    if content_str and ("router" in content_str.lower() or "route" in content_str.lower() or "BrowserRouter" in content_str) and ("route" in filename.lower() or "router" in filename.lower()):
        return "Defines the primary routing configuration"
    
    # 7. Root-level configuration file that affects the entire build
    if filename in {"next.config.js", "vite.config.ts", "tailwind.config.ts", "tsconfig.json", "webpack.config.js", "package.json", "requirements.txt", "pyproject.toml"}:
        return "Root-level configuration file that affects the entire build"
    
    # 8. Defines shared TypeScript types or interfaces used across 5+ files
    if ext in {".ts", ".tsx"} and ("type " in content_str or "interface " in content_str) and "types" in filename.lower():
        # Requires 5+ files, but we don't have separate count for types. We'll use import_count.
        pass

    return None

def main():
    os.makedirs(os.path.join(PROJECT_ROOT, "codebase-context", "summary-version"), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "codebase-context", "full-version"), exist_ok=True)
    
    all_files = []
    
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        
        for f in files:
            if is_excluded_file(f):
                continue
                
            filepath = os.path.join(root, f)
            relpath = os.path.relpath(filepath, PROJECT_ROOT).replace("\\", "/")
            all_files.append({"filepath": filepath, "relpath": relpath, "filename": f})

    # Read contents of non-binary files
    file_contents = {}
    for f_info in all_files:
        ext = os.path.splitext(f_info["filename"])[1].lower()
        if ext in BINARY_EXTS:
            continue
        try:
            with open(f_info["filepath"], "r", encoding="utf-8") as file:
                file_contents[f_info["relpath"]] = file.read()
        except:
            pass

    # Find imports
    import_counts = {f["relpath"]: 0 for f in all_files}
    for content in file_contents.values():
        for f_info in all_files:
            if f_info["relpath"] not in file_contents: # skip checking binary for imports
                continue
            basename_no_ext = os.path.splitext(f_info["filename"])[0]
            if basename_no_ext == "index" or len(basename_no_ext) < 3:
                # Be more precise for index files or very short names
                if f"/{basename_no_ext}" in content or f_info["filename"] in content:
                    import_counts[f_info["relpath"]] += 1
            else:
                if basename_no_ext in content:
                    import_counts[f_info["relpath"]] += 1

    manifest_files = []
    critical_files = []
    
    for i, f_info in enumerate(all_files):
        ext = os.path.splitext(f_info["filename"])[1].lower()
        is_binary = ext in BINARY_EXTS
        category = get_category(f_info["filename"], is_binary)
        
        import_count = import_counts[f_info["relpath"]] if not is_binary else None
        
        content = file_contents.get(f_info["relpath"], "")
        critical_reason = determine_critical_reason(f_info["filepath"], import_count, content)
        is_critical = critical_reason is not None
        
        if is_critical:
            critical_files.append({"relpath": f_info["relpath"], "reason": critical_reason, "import_count": import_count})
        
        manifest_files.append({
            "id": i + 1,
            "path": f_info["relpath"],
            "extension": ext,
            "category": category,
            "is_binary": is_binary,
            "is_critical": is_critical,
            "critical_reason": critical_reason,
            "import_count": import_count,
            "status": "pending",
            "documented_in_index": False,
            "documented_in_full_version": False,
            "documented_in_summary": False
        })
    
    code_files = sum(1 for f in manifest_files if f["category"] == "code")
    binary_files = sum(1 for f in manifest_files if f["is_binary"])
    
    manifest_data = {
        "session_id": SESSION_ID,
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "project_type": "Python FastAPI + Next.js / Node.js Full-Stack Application",
        "is_monorepo": True,
        "monorepo_workspaces": [
            "client-test-app", "dashboard", "examples/host-backend",
            "examples/web-client", "sdk", "sdk-server", "telephony"
        ],
        "total_files": len(manifest_files),
        "code_files": code_files,
        "binary_files": binary_files,
        "critical_files_count": len(critical_files),
        "excluded_dirs": list(EXCLUDED_DIRS),
        "excluded_files": list(EXCLUDED_FILES),
        "files": manifest_files
    }
    
    with open(os.path.join(PROJECT_ROOT, "codebase-context", "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
        
    print(f"I found {len(manifest_files)} total files to document ({code_files} code files, {binary_files} binary files). Many lock/generated files excluded.")
    for cf in critical_files:
        print(f"Marking as CRITICAL: {cf['relpath']} — Reason: {cf['reason']}")
        
    # Generate 00_PROJECT_OVERVIEW.md
    overview_content = f"""---
session_id: {SESSION_ID}
generated_at: {datetime.now(timezone.utc).isoformat() + "Z"}
step: 1 of 7
total_files: {len(manifest_files)}
code_files: {code_files}
binary_files: {binary_files}
critical_files: {len(critical_files)}
---

# Project Overview

## Detected Project Type
Python FastAPI + Next.js / Node.js full-stack application using LiveKit, Supabase, and various SDKs.

## Monorepo
Yes — Workspaces: client-test-app, dashboard, examples/host-backend, examples/web-client, sdk, sdk-server, telephony

## Complete Tech Stack
- **fastapi** v0.139.0 — Python API framework for the backend services
- **livekit** v1.1.13 — Real-time WebRTC backend and server communication
- **livekit-agents** v1.6.5 — Framework for LiveKit conversational AI agents
- **livekit-plugins-cartesia** v1.6.5 — Cartesia TTS plugin for LiveKit
- **livekit-plugins-deepgram** v1.6.5 — Deepgram STT plugin for LiveKit
- **livekit-plugins-elevenlabs** v1.6.5 — ElevenLabs TTS plugin for LiveKit
- **livekit-plugins-openai** v1.6.5 — OpenAI LLM plugin for LiveKit
- **google-genai** v2.12.1 — Google GenAI integrations
- **supabase** v2.31.0 — Python client for Supabase database/auth interaction
- **psycopg** v3.3.4 — PostgreSQL database adapter for Python
- **uvicorn** v0.51.0 — ASGI server for running FastAPI
- **pytest** v9.1.1 — Testing framework for Python

## Complete Folder Structure
```
"""
    # Build tree
    tree_lines = []
    def build_tree(dir_path, prefix=""):
        try:
            items = sorted(os.listdir(dir_path))
        except:
            return
        items = [item for item in items if item not in EXCLUDED_DIRS]
        
        for i, item in enumerate(items):
            if is_excluded_file(item):
                continue
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            tree_lines.append(prefix + connector + item)
            
            full_path = os.path.join(dir_path, item)
            if os.path.isdir(full_path):
                extension = "    " if is_last else "│   "
                build_tree(full_path, prefix + extension)
                
    build_tree(PROJECT_ROOT)
    overview_content += "\\n".join(tree_lines) + "\\n```"
    
    overview_content += """

## Architecture Overview
- **Overall pattern:** Microservices-based monorepo with multiple independent services (telephony, worker, admin, sdk-server).
- **Frontend structure:** Separated web client testing apps and dashboards.
- **Routing:** Handled internally by FastAPI routers (for Python APIs).
- **Backend/API:** Python backend exposing REST and WebSockets (via FastAPI and livekit).
- **Authentication:** Integrated with Supabase and custom JWT handling (PyJWT).
- **Data fetching:** httpx and native Python request libraries; livekit SDK.
- **State management:** Managed independently in frontends, backed by Supabase DB via psycopg.
- **External services:** LiveKit, Supabase, OpenAI, ElevenLabs, Deepgram, Cartesia.

## Data Flow Diagram
```
User Action
    │
    ▼
[Web/Client App] ──→ [LiveKit Server / WebRTC]
                                │
                                ▼
                        [Python Worker/Agent]
                                │
                                ▼
                       [Supabase Postgres DB]
                                │
          ◄─────────────────────┘
     [Response/Stream back to client]
```

## Critical Files
"""
    for cf in critical_files:
        overview_content += f"- `{cf['relpath']}` — {cf['reason']} — imported by {cf['import_count'] if cf['import_count'] else 0} files\\n"
        
    overview_content += """
## Key Patterns & Conventions Observed
- Naming conventions: snake_case for Python modules and variables, camelCase/PascalCase for TypeScript components.
- File naming: Modularized per feature/service.
- Import style: standard relative and absolute imports according to language standards.
- Error handling: try/except in Python.
"""
    
    with open(os.path.join(PROJECT_ROOT, "codebase-context", "00_PROJECT_OVERVIEW.md"), "w", encoding="utf-8") as f:
        f.write(overview_content)
        
    # Update .gitignore
    gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
    updated_gitignore = False
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "codebase-context/" not in content:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\n# CodeContext — auto-generated LLM documentation (do not commit)\ncodebase-context/\n")
            updated_gitignore = True
            print(".gitignore updated")
        else:
            print(".gitignore already contained codebase-context/")
    else:
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("# CodeContext — auto-generated LLM documentation (do not commit)\ncodebase-context/\n")
        updated_gitignore = True
        print(".gitignore created new")
        
    # Create PROGRESS.json
    progress_data = {
      "session_id": SESSION_ID,
      "last_updated": datetime.now(timezone.utc).isoformat() + "Z",
      "steps": {
        "01_SCAN": {
          "status": "complete",
          "completed_at": datetime.now(timezone.utc).isoformat() + "Z",
          "total_files": len(manifest_files),
          "critical_files": len(critical_files),
          "notes": ""
        },
        "02_INDEX": { "status": "pending", "completed_at": None, "files_documented": 0 },
        "03_DATABASE": { "status": "pending", "completed_at": None, "db_type": None, "tables_documented": 0 },
        "04_ENV": { "status": "pending", "completed_at": None, "variables_documented": 0 },
        "05_SUMMARY": { "status": "pending", "completed_at": None, "token_estimate": None, "split": False },
        "06_FULL": { "status": "pending", "completed_at": None, "layers_created": 0, "files_documented": 0 },
        "07_AUDIT": { "status": "pending", "completed_at": None, "verdict": None, "issues_found": 0 }
      }
    }
    
    with open(os.path.join(PROJECT_ROOT, "codebase-context", "PROGRESS.json"), "w", encoding="utf-8") as f:
        json.dump(progress_data, f, indent=2)

if __name__ == "__main__":
    main()
