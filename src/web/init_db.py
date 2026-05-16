import time

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from config import DATABASE_URL

RETRY_MAX = 10
RETRY_DELAY = 2  # seconds


def _wait_for_db():
    for attempt in range(1, RETRY_MAX + 1):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.close()
            return
        except Exception:
            if attempt < RETRY_MAX:
                time.sleep(RETRY_DELAY)
            else:
                raise


def create_tables():
    _wait_for_db()
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'admin' NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bots (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            code TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS game_results (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            bot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
            opponent_type VARCHAR(20) NOT NULL,
            opponent_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
            result VARCHAR(10) NOT NULL,
            user_score INTEGER NOT NULL,
            opponent_score INTEGER NOT NULL,
            turns INTEGER NOT NULL,
            played_at TIMESTAMP DEFAULT NOW()
        );
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tournaments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP
        );
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_games (
            id SERIAL PRIMARY KEY,
            tournament_id INTEGER REFERENCES tournaments(id) ON DELETE CASCADE,
            bot1_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
            bot2_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
            bot1_name VARCHAR(100) NOT NULL,
            bot2_name VARCHAR(100) NOT NULL,
            game_order INTEGER NOT NULL,
            bot1_score INTEGER DEFAULT 0,
            bot2_score INTEGER DEFAULT 0,
            winner INTEGER,
            turns INTEGER DEFAULT 0,
            played_at TIMESTAMP DEFAULT NOW()
        );
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_results (
            id SERIAL PRIMARY KEY,
            tournament_id INTEGER REFERENCES tournaments(id) ON DELETE CASCADE,
            bot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
            bot_name VARCHAR(100) NOT NULL,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0
        );
    """
    )

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bots_user_id ON bots(user_id);")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_game_results_user_id ON game_results(user_id);"
    )

    cursor.close()
    conn.close()
    print("Database tables created successfully!")


def migrate_role_column():
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'admin' NOT NULL"
        )
    except Exception as e:
        print(f"Migration role column: {e}")
    finally:
        conn.close()


def migrate_winrate_column():
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS winrate INTEGER")
    except Exception as e:
        print(f"Migration winrate column: {e}")
    finally:
        conn.close()


def ensure_default_admin():
    from config import ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD
    from web.auth import create_default_admin_if_not_exists

    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users LIMIT 1")
    conn.close()

    from web.models import SessionLocal

    db = SessionLocal()
    try:
        admin = create_default_admin_if_not_exists(
            db, ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD
        )
        if admin:
            print(f"Admin account ready: {admin.username}")
    finally:
        db.close()


if __name__ == "__main__":
    create_tables()
    migrate_role_column()
    migrate_winrate_column()
    ensure_default_admin()
