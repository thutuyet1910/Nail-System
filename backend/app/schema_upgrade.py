"""One-time, repeatable upgrade of an existing Check-In database: a customer's birth date may be unknown.

A customer who was first recorded from an appointment (booked by phone, by the AI receptionist or by staff) has no birth date on file, and the
kiosk must not invent one. SQLite cannot drop a NOT NULL rule from a column, so the customers table is rebuilt the way SQLite documents it:
new table, copy every row, drop the old one, rename, recreate the indexes, check the foreign keys, all in ONE transaction. Any problem rolls the
whole thing back and leaves the database exactly as it was. A database that already allows an unknown birth date is not touched.
"""

import logging
import re

logger = logging.getLogger("nail_system.schema_upgrade")


def make_birth_date_optional(engine) -> bool:
    """Returns True when the table was rebuilt, False when nothing had to change."""
    with engine.connect() as connection:
        columns = connection.exec_driver_sql("PRAGMA table_info(customers)").fetchall()
    birth_date = next((row for row in columns if row[1] == "date_of_birth"), None)
    if birth_date is None or birth_date[3] == 0:  # no such table/column yet (a new database), or already optional
        return False

    raw = engine.raw_connection()
    driver = raw.driver_connection
    previous_isolation = driver.isolation_level
    driver.isolation_level = None  # this function manages its own transaction
    cursor = driver.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN IMMEDIATE")
        try:
            definition = cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='customers'").fetchone()[0]
            indexes = [row[0] for row in cursor.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='customers' AND sql IS NOT NULL")]
            relaxed, changed = re.subn(r"(date_of_birth\s+DATE)\s+NOT\s+NULL", r"\1", definition, count=1, flags=re.IGNORECASE)
            renamed, named = re.subn(r'CREATE\s+TABLE\s+"?customers"?', "CREATE TABLE customers_new", relaxed, count=1, flags=re.IGNORECASE)
            if not changed or not named:
                raise RuntimeError("the customers table has an unexpected definition")
            cursor.execute(renamed)
            cursor.execute("INSERT INTO customers_new SELECT * FROM customers")
            copied = cursor.execute("SELECT COUNT(*) FROM customers_new").fetchone()[0]
            original = cursor.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
            if copied != original:
                raise RuntimeError("not every customer was copied")
            cursor.execute("DROP TABLE customers")
            cursor.execute("ALTER TABLE customers_new RENAME TO customers")
            for statement in indexes:
                cursor.execute(statement)
            problems = cursor.execute("PRAGMA foreign_key_check").fetchall()
            if problems:
                raise RuntimeError("the rebuilt table breaks a foreign key")
            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            raise
        logger.info("Customers may now have an unknown birth date (%d customers kept).", original)
        return True
    finally:
        cursor.execute("PRAGMA foreign_keys=ON")
        driver.isolation_level = previous_isolation
        raw.close()
