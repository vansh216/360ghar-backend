"""Upload real floor plan images to Cloudinary and fix broken floor_plan_urls.

RCA (2026-06-17)
----------------
During seeding, ``_set_floor_plan()`` did ``media_urls.get(media_ref, media_ref)``.
When the floor plan upload failed (or the media_ref wasn't in the map), the
raw ``media/hc_properties/<slug>/floor_plan.png`` string was stored as the
URL. ``fix_relative_image_urls.py`` later converted these to absolute
Cloudinary URLs, but the underlying files were never uploaded. Result:
94 of 109 floor_plan_urls return HTTP 404 (15 uploaded successfully).

This script:
1. Finds every property with a broken (non-versioned ``hc_properties``) floor_plan_url.
2. Locates the matching real ``floor_plan.png`` in
   ``seed_data/hardcoded/properties/<slug>/floor_plan.png``.
3. Uploads each to Cloudinary at ``360ghar/properties/<property_id>/floor_plan.webp``
   (matching the working image pattern), optimizing to WebP.
4. Updates ``properties.floor_plan_url`` to the returned secure_url.

Idempotent: skips rows whose floor_plan_url already uses the working
``/image/upload/v`` pattern.

Usage::

    cd backend
    source .venv/bin/activate
    python scripts/fix_floor_plan_urls.py           # dry-run (default)
    python scripts/fix_floor_plan_urls.py --apply   # upload + commit
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env.dev")

# Real floor plan source images.
HARDCODED_DIR = (
    Path(__file__).resolve().parent.parent / "seed_data" / "hardcoded" / "properties"
)
BROKEN_SIG = "%/image/upload/360ghar/hc_properties/%"


def _engine():
    from sqlalchemy import create_engine

    url = os.environ["DATABASE_URL"]
    if "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url)


def _discover(eng) -> list[tuple[int, str, Path]]:
    """Return [(property_id, slug, local_path), ...] for broken floor plans.

    Aborts if any broken row has no matching local floor_plan.png.
    """
    from sqlalchemy import text

    rows = []
    with eng.connect() as c:
        db_rows = c.execute(
            text(
                "SELECT id, floor_plan_url FROM properties "
                "WHERE floor_plan_url LIKE :sig ORDER BY id"
            ),
            {"sig": BROKEN_SIG},
        ).fetchall()

    missing: list[tuple[int, str]] = []
    for pid, url in db_rows:
        m = re.search(r"/(\d{5}-[^/]+)/floor_plan", url)
        if not m:
            missing.append((pid, f"NO_SLUG_IN_URL:{url[:80]}"))
            continue
        slug = m.group(1)
        local = HARDCODED_DIR / slug / "floor_plan.png"
        if not local.exists():
            missing.append((pid, str(local)))
            continue
        rows.append((pid, slug, local))

    if missing:
        print("ERROR: no local floor_plan.png for some broken rows; aborting.", file=sys.stderr)
        for pid, hint in missing[:20]:
            print(f"  prop {pid}: {hint}", file=sys.stderr)
        sys.exit(1)

    return rows


def _upload_one(local_path: Path, property_id: int) -> str:
    """Upload a floor plan to Cloudinary, return the secure_url.

    Uses the working ``360ghar/properties/<id>/`` folder pattern and
    optimizes to WebP, matching how property images are stored.

    Note: ``CloudinaryService.upload_file`` already prepends the root
    (``360ghar``) and appends the format, so we pass ``folder=None`` and
    a public_id WITHOUT extension to avoid ``360ghar/360ghar/.../x.webp.jpg``.
    """
    from app.services.cloudinary import cloudinary_service
    from app.services.image_processing import optimize_for_web

    file_bytes = local_path.read_bytes()
    try:
        optimized, content_type = optimize_for_web(
            file_bytes, max_dimension=2048, quality=85
        )
        if optimized is not None:
            file_bytes = optimized
    except Exception as exc:
        print(f"  WARNING: optimization failed for {local_path.name}: {exc}; using original")
        content_type = "image/png"

    # No extension in public_id: Cloudinary appends the real format (.webp).
    # No folder arg: upload_file prepends the ``360ghar`` root automatically.
    public_id = f"properties/{property_id}/floor_plan"

    result = cloudinary_service.upload_file(
        file_bytes=file_bytes,
        public_id=public_id,
        folder=None,
        content_type=content_type or "image/png",
        is_image=True,
        overwrite=True,
    )
    return result["secure_url"]


async def _upload_all(items: list[tuple[int, str, Path]]) -> dict[int, str]:
    """Upload all floor plans concurrently (bounded). Returns {property_id: url}."""
    semaphore = asyncio.Semaphore(5)
    results: dict[int, str] = {}

    async def _one(pid: int, slug: str, local: Path) -> None:
        async with semaphore:
            loop = asyncio.get_event_loop()
            try:
                url = await loop.run_in_executor(None, _upload_one, local, pid)
                results[pid] = url
                print(f"  uploaded prop {pid}: {slug} -> {url}")
            except Exception as exc:
                print(f"  FAILED prop {pid}: {slug}: {exc}", file=sys.stderr)

    await asyncio.gather(*[_one(pid, slug, local) for pid, slug, local in items])
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload real floor plan images and fix broken floor_plan_urls."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upload to Cloudinary and commit DB updates (default is dry-run).",
    )
    args = parser.parse_args()

    eng = _engine()
    items = _discover(eng)
    if not items:
        print("No broken floor_plan_url rows found. Nothing to do.")
        return

    print(f"\nBroken floor_plan_url rows: {len(items)}")
    print("Sample (first 10):")
    for pid, slug, local in items[:10]:
        print(f"  prop {pid}: {slug}")
        print(f"    local: {local}")
    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")

    if not args.apply:
        print("\n*** DRY RUN -- no uploads or DB changes. Re-run with --apply to commit. ***")
        return

    # Upload all floor plans to Cloudinary.
    print(f"\nUploading {len(items)} floor plans to Cloudinary...")
    url_map = asyncio.run(_upload_all(items))
    print(f"\nUploaded successfully: {len(url_map)} / {len(items)}")

    if len(url_map) != len(items):
        print(
            f"WARNING: {len(items) - len(url_map)} upload(s) failed; "
            "those rows will not be updated.",
            file=sys.stderr,
        )

    if not url_map:
        print("No successful uploads; aborting DB update.")
        sys.exit(1)

    # Update DB floor_plan_url for each successfully uploaded property.
    from sqlalchemy import text

    updated = 0
    with eng.begin() as c:
        for pid, url in url_map.items():
            c.execute(
                text("UPDATE properties SET floor_plan_url = :url WHERE id = :id"),
                {"url": url, "id": pid},
            )
            updated += 1

    print(f"\n*** Done. Updated {updated} floor_plan_url rows. ***")
    print("Remaining broken rows:",
          len(items) - len(url_map), "(due to upload failures)")


if __name__ == "__main__":
    main()
