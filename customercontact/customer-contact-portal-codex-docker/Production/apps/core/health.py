from django.db import DatabaseError, connection


def database_is_healthy(db_connection=None):
    db_connection = db_connection or connection
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return False
    return True
