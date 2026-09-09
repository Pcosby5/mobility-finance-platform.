"""Preserve existing users and all PostgreSQL foreign keys while changing their IDs."""

import uuid

from django.db import migrations, models


def convert_user_ids(apps, schema_editor):
    connection = schema_editor.connection
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        # Capture definitions before dropping constraints so their original behaviour survives.
        cursor.execute(
            """
            SELECT ns.nspname, rel.relname, attr.attname, con.conname,
                   pg_get_constraintdef(con.oid), cardinality(con.conkey)
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = rel.relnamespace
            JOIN pg_attribute attr ON attr.attrelid = con.conrelid
                AND attr.attnum = con.conkey[1]
            WHERE con.contype = 'f' AND con.confrelid = 'users_user'::regclass
            ORDER BY ns.nspname, rel.relname, con.conname
            """
        )
        references = cursor.fetchall()
        if any(row[5] != 1 for row in references):
            raise RuntimeError("UUID migration requires single-column user foreign keys.")

        tables = sorted({f"{quote(row[0])}.{quote(row[1])}" for row in references})
        cursor.execute(
            "LOCK TABLE " + ", ".join(['"users_user"', *tables]) + " IN ACCESS EXCLUSIVE MODE"
        )
        cursor.execute(
            "CREATE TEMP TABLE user_uuid_map (old_id bigint PRIMARY KEY, new_id uuid UNIQUE) "
            "ON COMMIT DROP"
        )
        cursor.execute('SELECT id FROM "users_user"')
        user_ids = cursor.fetchall()
        cursor.executemany(
            "INSERT INTO user_uuid_map (old_id, new_id) VALUES (%s, %s)",
            [(row[0], uuid.uuid4()) for row in user_ids],
        )
        # ALTER COLUMN USING cannot contain a subquery; a temporary function performs the lookup.
        cursor.execute(
            """
            CREATE FUNCTION pg_temp.user_uuid(original_id bigint) RETURNS uuid
            LANGUAGE sql STRICT AS
            'SELECT new_id FROM pg_temp.user_uuid_map WHERE old_id = $1'
            """
        )
        for namespace, table, column, constraint, definition, _ in references:
            qualified = f"{quote(namespace)}.{quote(table)}"
            cursor.execute(f"ALTER TABLE {qualified} DROP CONSTRAINT {quote(constraint)}")

        cursor.execute('ALTER TABLE "users_user" ALTER COLUMN "id" DROP IDENTITY IF EXISTS')
        cursor.execute('ALTER TABLE "users_user" ALTER COLUMN "id" DROP DEFAULT')
        cursor.execute(
            'ALTER TABLE "users_user" ALTER COLUMN "id" TYPE uuid USING pg_temp.user_uuid(id)'
        )
        converted = set()
        for namespace, table, column, constraint, definition, _ in references:
            qualified = f"{quote(namespace)}.{quote(table)}"
            key = (namespace, table, column)
            if key not in converted:
                cursor.execute(
                    f"ALTER TABLE {qualified} ALTER COLUMN {quote(column)} TYPE uuid "
                    f"USING pg_temp.user_uuid({quote(column)})"
                )
                converted.add(key)
        for namespace, table, column, constraint, definition, _ in references:
            qualified = f"{quote(namespace)}.{quote(table)}"
            cursor.execute(
                f"ALTER TABLE {qualified} ADD CONSTRAINT {quote(constraint)} {definition}"
            )
        cursor.execute(
            """
            UPDATE django_admin_log log SET object_id = mapping.new_id::text
            FROM pg_temp.user_uuid_map mapping, django_content_type content_type
            WHERE log.content_type_id = content_type.id
              AND content_type.app_label = 'users' AND content_type.model = 'user'
              AND log.object_id = mapping.old_id::text
            """
        )
        cursor.execute("DROP FUNCTION pg_temp.user_uuid(bigint)")

    # Session payloads contain the old integer ID. Force a fresh login without changing accounts.
    apps.get_model("sessions", "Session").objects.using(connection.alias).all().delete()


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ("users", "0001_initial"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("sessions", "0001_initial"),
        ("token_blacklist", "0013_alter_blacklistedtoken_options_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(convert_user_ids)],
            state_operations=[
                migrations.AlterField(
                    model_name="user",
                    name="id",
                    field=models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
            ],
        ),
    ]
