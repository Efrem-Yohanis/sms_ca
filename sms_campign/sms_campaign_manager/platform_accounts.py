from django.db import connection


def get_platform_profile(user_id):
    with connection.cursor() as cursor:
        if "admin_control_userprofile" not in connection.introspection.table_names(cursor):
            return None
        cursor.execute(
            "SELECT role, require_password_change FROM admin_control_userprofile WHERE user_id = %s",
            [user_id],
        )
        return cursor.fetchone()


def clear_password_change_requirement(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE admin_control_userprofile "
            "SET require_password_change = FALSE, updated_at = CURRENT_TIMESTAMP "
            "WHERE user_id = %s AND require_password_change = TRUE",
            [user_id],
        )
        return cursor.rowcount == 1
