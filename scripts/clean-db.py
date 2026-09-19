import psycopg2

DATABASE_URL = "postgresql://cardcube:TPAdhfnyLmLptJxx@152.70.238.24:5432/cardcube"

TABLES_TO_TRUNCATE = [
    "change_log",
    "email_attachments",
    "statement_drafts",
    "statement_versions",
    "payments",
    "statements",
    "cards",
    "accounts",
    "email_sources",
    "mail_jobs",
    "mail_cursors",
    "devices",
]

def main():
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        tables_str = ", ".join(TABLES_TO_TRUNCATE)
        cur.execute(f"TRUNCATE TABLE {tables_str} CASCADE;")
        cur.execute("ALTER SEQUENCE change_seq RESTART WITH 1;")
        cur.execute("UPDATE mailboxes SET status = 'active', error_message = NULL WHERE email_address = 'ourpurple@sina.com';")
        conn.commit()
        print("Successfully truncated tables and reset change_seq sequence.")

        print("\nVerifying row counts:")
        for t in TABLES_TO_TRUNCATE:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            count = cur.fetchone()[0]
            print(f"  {t}: {count}")

        cur.execute("SELECT version_num FROM alembic_version")
        ver = cur.fetchone()[0]
        print(f"\nAlembic version preserved: {ver}")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
