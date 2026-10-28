"""Build a standard OCI image with an optional Coders fast-start payload."""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

RUNTIMES = {
    "python-3.12": (
        "python-3.12-bookworm-v1",
        "python@sha256:62ed8e07e544e8555c5d93748d5275015136b7f5c52b5e8679b4de339c3779d3",
    ),
    "nodejs-22": (
        "nodejs-22-bookworm-v1",
        "node@sha256:3ed748ce9dea62d2f0f0205cdbb6823106d9f973a6f555c402fe2575f8d6e1ae",
    ),
}


def dockerfile(runtime, start, build=None):
    release, image = RUNTIMES[runtime]
    command = shlex.split(start)
    if not command or len(command) > 32 or any(len(s) > 1024 or "\0" in s for s in command):
        raise ValueError("Use a nonempty, bounded start command")
    node = runtime.startswith("nodejs")
    default = (
        "npm ci && npm run build --if-present && npm prune --omit=dev"
        if node
        else "if [ -f uv.lock ]; then pip install --no-cache-dir uv && "
        "uv export --frozen --no-dev --no-editable --output-file=/tmp/requirements.txt && "
        "pip install --no-cache-dir --target=/app/.python -r /tmp/requirements.txt; "
        "elif [ -f requirements.txt ]; then "
        "pip install --no-cache-dir --target=/app/.python -r requirements.txt; "
        "elif [ -f pyproject.toml ]; then pip install --no-cache-dir --target=/app/.python .; fi"
    )
    label = json.dumps(
        {"version": 1, "runtime": release, "command": command}, separators=(",", ":")
    )
    return "\n".join(
        [
            "FROM " + image + " AS build",
            "WORKDIR /app",
            "COPY app/ /app/",
            "RUN " + (build or default),
            "FROM " + image,
            "WORKDIR /app",
            "COPY --from=build /app/ /app/",
            "ENV PYTHONPATH=/app/.python",
            "ENV PATH=/app/.python/bin:/app/node_modules/.bin:$PATH",
            "LABEL kr.coders.fast-start=" + json.dumps(label),
            "CMD " + json.dumps(command),
            "",
        ]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, choices=RUNTIMES)
    parser.add_argument("--start", required=True)
    parser.add_argument("--build")
    parser.add_argument("--context", default=".")
    parser.add_argument("--image", default="ghcr.io/" + os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--push", action="store_true")
    options = parser.parse_args()
    image = options.image.lower()
    if not re.fullmatch(r"ghcr\.io/[a-z0-9_.-]+/[a-z0-9_./-]+", image):
        parser.error("Use a GHCR package name without a tag")
    commit = (
        os.getenv("GITHUB_SHA")
        or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    )
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        parser.error("A full Git commit is required")
    with tempfile.TemporaryDirectory(prefix="coders-fast-build-") as directory:
        root = Path(directory)
        shutil.copytree(
            Path(options.context).resolve(),
            root / "app",
            symlinks=True,
            ignore=shutil.ignore_patterns(
                ".git", ".env", ".env.*", ".venv", "node_modules", "__pycache__", ".pytest_cache"
            ),
        )
        (root / "Dockerfile").write_text(dockerfile(options.runtime, options.start, options.build))
        metadata = root / "metadata.json"
        subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                "--platform=linux/amd64",
                "--provenance=false",
                "--metadata-file",
                str(metadata),
                "--tag",
                image + ":sha-" + commit,
                "--push" if options.push else "--load",
                str(root),
            ],
            check=True,
        )
        digest = json.loads(metadata.read_text())["containerimage.digest"]
        if output := os.getenv("GITHUB_OUTPUT"):
            with open(output, "a") as stream:
                stream.write("image=" + image + "\ndigest=" + digest + "\n")
        print(image + "@" + digest)


if __name__ == "__main__":
    main()
