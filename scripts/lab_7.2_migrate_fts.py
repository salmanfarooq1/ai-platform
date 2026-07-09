"""
scripts/lab_7.2_migrate_fts.py

Applies the Week 7 full-text search migration to the running database:
  1. Add fts_vector column (idempotent - no-op if it already exists)
  2. Backfill fts_vector for all existing rows
  3. Create GIN index on fts_vector
  4. Create/replace the trigger function + trigger to keep future rows in sync
  5. Verify: run a test tsquery, confirm it returns results

Safe to re-run — every statement is idempotent.
"""
import asyncio
import time

from core.database.pool import create_pool


async def column_exists(conn, table: str, column: str) -> bool:
    row = await conn.fetchrow(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = $1 AND column_name = $2
        """,
        table,
        column,
    )
    return row is not None


async def migrate(pool):
    async with pool.acquire() as conn:
        # Step 1: Add column
        already_had_column = await column_exists(conn, "documents", "fts_vector")
        await conn.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS fts_vector tsvector"
        )
        print(
            f"[1/5] fts_vector column: "
            f"{'already existed' if already_had_column else 'created'}"
        )

        # Step 2: Backfill existing rows
        row_count = await conn.fetchval("SELECT count(*) FROM documents")
        print(f"[2/5] Backfilling fts_vector for {row_count} rows...")
        start = time.perf_counter()
        result = await conn.execute(
            """
            UPDATE documents
            SET fts_vector = to_tsvector('english', coalesce(content, ''))
            """
        )
        elapsed = time.perf_counter() - start
        print(f"      Done in {elapsed:.3f}s ({result})")

        # Step 3: GIN index
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_documents_fts
                ON documents USING GIN (fts_vector)
            """
        )
        print("[3/5] Created GIN index idx_documents_fts")

        # Step 4: Trigger function + trigger
        await conn.execute(
            """
            CREATE OR REPLACE FUNCTION update_fts_vector()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.fts_vector := to_tsvector('english', coalesce(NEW.content, ''));
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        await conn.execute("DROP TRIGGER IF EXISTS trig_update_fts ON documents")
        await conn.execute(
            """
            CREATE TRIGGER trig_update_fts
                BEFORE INSERT OR UPDATE ON documents
                FOR EACH ROW EXECUTE FUNCTION update_fts_vector()
            """
        )
        print("[4/5] Created trigger trig_update_fts")

        # Step 5: Verification
        check = await conn.fetchval(
            """
            SELECT count(*) FROM documents
            WHERE fts_vector @@ to_tsquery('english', 'data & retention')
            """
        )
        print(f"[5/5] Verification query ('data & retention'): {check} matching rows")

        if check == 0:
            print(
                "      WARNING: 0 matches. Either the corpus has no such terms, "
                "or something in the migration didn't apply correctly."
            )


async def main():
    pool = await create_pool()
    try:
        await migrate(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
