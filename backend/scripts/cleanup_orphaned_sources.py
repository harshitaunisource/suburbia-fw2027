"""
One-time cleanup after scripts.migrate_add_buyers: reconciles the old
"orphaned" generic_source_configs rows (buyer_id IS NULL, left over from
before the buyer/competitor feature existed) with the new, properly
buyer-attached duplicate rows that scripts.seed_buyers_master_data just
created for the same (brand, category_url).

IMPORTANT DIRECTION: this fixes the ORPHAN in place (sets its buyer_id
and role) and deletes the freshly-SEEDED duplicate instead -- not the
other way around. The orphan is very likely the row real scrape history
points at (GenericScrapeRun.source_config_id, GenericProduct.source_config_id
both foreign-key to generic_source_configs.id), since it's the one that
existed when any earlier scrape was run from the old, buyer-less version
of this feature. The seeded duplicate is brand new and has no history,
so it's always safe to remove. Doing it the other way around (deleting
the orphan) is exactly what failed for you with a ForeignKeyViolation on
generic_scrape_runs -- this script avoids that by construction.

For each orphan, before deleting its duplicate this script re-checks
that the duplicate truly has zero scrape runs / products referencing it
(should always be true for something the seed script just created, but
checked explicitly rather than assumed). If that ever isn't true, the
duplicate is left alone and reported instead of deleted -- you'd then
have two valid, buyer-attached rows for the same brand+URL, which is
harmless (just remove one manually via the API/UI whenever convenient).

Only one row is fixed/deleted per iteration, each in its own commit --
so if any single pair has a problem, every other pair still gets
processed instead of the whole run aborting.

Safe to re-run: once no orphans remain, running this again just reports
"nothing to clean up".

Run this AFTER scripts.seed_buyers_master_data.

Usage:
    cd backend
    python -m scripts.cleanup_orphaned_sources
"""
from app.database import SessionLocal, init_db
from app.models import GenericProduct, GenericScrapeRun, GenericSourceConfig


def _reference_count(db, source_config_id: int) -> int:
    runs = (
        db.query(GenericScrapeRun)
        .filter(GenericScrapeRun.source_config_id == source_config_id)
        .count()
    )
    products = (
        db.query(GenericProduct)
        .filter(GenericProduct.source_config_id == source_config_id)
        .count()
    )
    return runs + products


def cleanup():
    init_db()
    db = SessionLocal()
    try:
        orphans = (
            db.query(GenericSourceConfig)
            .filter(GenericSourceConfig.buyer_id.is_(None))
            .all()
        )
        if not orphans:
            print("Nothing to clean up -- no orphaned (buyer_id IS NULL) rows found.")
            return

        fixed = 0
        duplicate_left_in_place = []
        no_match = []

        for orphan in orphans:
            matches = (
                db.query(GenericSourceConfig)
                .filter(
                    GenericSourceConfig.buyer_id.isnot(None),
                    GenericSourceConfig.brand == orphan.brand,
                    GenericSourceConfig.category_url == orphan.category_url,
                )
                .all()
            )
            if len(matches) != 1:
                # Zero matches: nothing seeded to reconcile against.
                # More than one: ambiguous, don't guess -- leave for a human.
                no_match.append((orphan, len(matches)))
                continue

            duplicate = matches[0]
            try:
                # Reattach the historic row to the real buyer/role.
                orphan.buyer_id = duplicate.buyer_id
                orphan.role = duplicate.role
                db.commit()

                if _reference_count(db, duplicate.id) == 0:
                    db.delete(duplicate)
                    db.commit()
                    fixed += 1
                else:
                    # Shouldn't normally happen (the duplicate was just
                    # seeded), but if it does, don't delete -- report it.
                    duplicate_left_in_place.append((orphan, duplicate))
            except Exception as e:
                db.rollback()
                print(f"  SKIP id={orphan.id} ({orphan.brand!r}, {orphan.category_url!r}): {e}")

        print(f"Reattached {fixed} historic row(s) to their real buyer, removing the redundant seeded duplicate.")

        if duplicate_left_in_place:
            print(
                f"\n{len(duplicate_left_in_place)} orphan(s) were reattached, but their duplicate had "
                f"unexpected references and was left in place -- you now have two valid rows for these "
                f"(harmless; remove one manually whenever convenient):"
            )
            for orphan, duplicate in duplicate_left_in_place:
                print(f"  orphan id={orphan.id}, duplicate id={duplicate.id}: {orphan.brand!r} {orphan.category_url!r}")

        if no_match:
            print(
                f"\n{len(no_match)} orphaned row(s) had no single matching seeded duplicate and were left "
                f"untouched (still buyer_id = NULL, not usable until fixed by hand):"
            )
            for orphan, match_count in no_match:
                reason = "no match" if match_count == 0 else f"{match_count} ambiguous matches"
                print(f"  id={orphan.id} brand={orphan.brand!r} url={orphan.category_url!r} ({reason})")
    finally:
        db.close()


if __name__ == "__main__":
    cleanup()