"""Build a distributable test SDK without linking the independent client to source."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "sdk"
DEST = ROOT / "client-integration-test" / "packages"
VERSION = "1.1.1-humanization.0"


def main():
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit("npm is required")
    subprocess.run([npm, "run", "build"], cwd=SDK, check=True)
    DEST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="awaaz-client-sdk-") as temp:
        stage = Path(temp)
        package = json.loads((SDK / "package.json").read_text(encoding="utf-8"))
        package["version"] = VERSION
        package.pop("scripts", None)
        package.pop("devDependencies", None)
        (stage / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
        for name in ("dist", "README.md", "CHANGELOG.md"):
            source = SDK / name
            if source.is_dir():
                shutil.copytree(source, stage / name)
            else:
                shutil.copy2(source, stage / name)
        result = subprocess.run([npm, "pack", "--json", "--pack-destination", str(DEST)], cwd=stage, check=True, capture_output=True, text=True)
        packed = json.loads(result.stdout)[0]
    artifact = DEST / packed["filename"]
    files = [SDK / "package.json", SDK / "tsconfig.json", *sorted((SDK / "src").rglob("*.ts"))]
    manifest = {
        "package": package["name"], "version": VERSION,
        "distribution": "unpublished test snapshot; not an npm registry release",
        "artifact": artifact.name,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "integrity": packed["integrity"],
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    (DEST / "voice-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), "version": VERSION, "sha256": manifest["sha256"]}))


if __name__ == "__main__":
    main()
