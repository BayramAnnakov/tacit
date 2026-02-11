"""Run extraction on eval repos, generate CLAUDE.md, fetch ground truth, compare."""
import asyncio
import sys
import os
import json
import logging

logging.basicConfig(level=logging.WARNING)
sys.stdout.reconfigure(line_buffering=True)

import httpx
from pipeline import run_extraction, generate_claude_md
import database as db

TOKEN = os.environ.get("GITHUB_TOKEN", "")

REPOS = [
    ("langchain-ai", "langchain"),
    ("denoland", "deno"),
    ("prisma", "prisma"),
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_claude_md")
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def fetch_real_claude_md(owner: str, name: str) -> str | None:
    """Fetch the actual CLAUDE.md from the repo."""
    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3.raw",
    }
    paths_to_try = ["CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md", ".claude/AGENTS.md"]
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for path in paths_to_try:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{name}/contents/{path}",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                return resp.text
    return None


async def main():
    # Clean DB for fresh eval
    db_path = db.DB_PATH
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"  Removed old DB: {db_path}")
    await db.init_db()

    for owner, name in REPOS:
        await db.create_repo(owner, name)

    # Phase 1: Extract
    for owner, name in REPOS:
        repo = f"{owner}/{name}"
        print(f"\n{'='*60}")
        print(f"EXTRACTING: {repo}")
        print(f"{'='*60}")

        async for event in run_extraction(repo, TOKEN):
            etype = event.event_type
            msg = event.message or ""
            if etype in ("rule_found", "stage_change", "complete", "error", "progress"):
                tag = etype.upper().replace("_", " ")
                print(f"  [{tag}] {msg}", flush=True)

    # Phase 2: Generate + fetch ground truth + compare
    print(f"\n{'='*60}")
    print("GENERATING CLAUDE.MD AND COMPARING")
    print(f"{'='*60}")

    for owner, name in REPOS:
        repo = f"{owner}/{name}"
        repos = await db.list_repos()
        repo_record = next((r for r in repos if r["full_name"] == repo), None)
        if not repo_record:
            print(f"  SKIP {repo}: not found in DB")
            continue

        repo_id = repo_record["id"]

        # Generate CLAUDE.md
        print(f"\n--- {repo} ---")
        generated = await generate_claude_md(repo_id)
        gen_path = os.path.join(OUTPUT_DIR, f"{owner}_{name}_CLAUDE.md")
        with open(gen_path, "w") as f:
            f.write(generated)
        print(f"  Generated: {gen_path}")

        # Fetch ground truth
        real = await fetch_real_claude_md(owner, name)
        if real:
            real_path = os.path.join(OUTPUT_DIR, f"{owner}_{name}_REAL_CLAUDE.md")
            with open(real_path, "w") as f:
                f.write(real)
            print(f"  Ground truth: {real_path}")
        else:
            print(f"  Ground truth: NOT FOUND in repo")

        # Stats
        rules = await db.list_rules(repo_id=repo_id)
        source_counts = {}
        for r in rules:
            st = r.get("source_type", "unknown")
            source_counts[st] = source_counts.get(st, 0) + 1

        print(f"  Total rules: {len(rules)}")
        print(f"  By source: {json.dumps(source_counts)}")
        print(f"  Rules:")
        for r in rules:
            src = r["source_type"][:4]
            print(f"    [{r['category']:12s}] (conf={r['confidence']:.2f}, src={src}) {r['rule_text'][:90]}")

    print(f"\n{'='*60}")
    print("EVAL COMPLETE")
    print(f"{'='*60}")
    print(f"Generated files in: {OUTPUT_DIR}")
    print("Compare generated vs real CLAUDE.md to measure coverage and precision.")


asyncio.run(main())
