from datetime import timedelta
from uuid import UUID, uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class UserUUIDMigrationTests(TransactionTestCase):
    def test_existing_users_and_related_records_survive_conversion(self):
        # An isolated schema lets us test the old database without reversing this data migration.
        schema = "uuid_migration_" + uuid4().hex
        quote = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute("SHOW search_path")
            original_path = cursor.fetchone()[0]
            cursor.execute(f"CREATE SCHEMA {quote(schema)}")
            cursor.execute(f"SET search_path TO {quote(schema)}")
        try:
            before = [
                ("users", "0001_initial"),
                ("admin", "0003_logentry_add_action_flag_choices"),
                ("sessions", "0001_initial"),
                ("token_blacklist", "0013_alter_blacklistedtoken_options_and_more"),
            ]
            executor = MigrationExecutor(connection)
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            user = old.get_model("users", "User").objects.create(
                username="existing", password="preserve-this-hash", role="OPERATIONS"
            )
            group = old.get_model("auth", "Group").objects.create(name="Existing group")
            user.groups.add(group)
            content_type = old.get_model("contenttypes", "ContentType").objects.create(
                app_label="users", model="user"
            )
            permission = old.get_model("auth", "Permission").objects.create(
                content_type=content_type, codename="view_user", name="Can view user"
            )
            user.user_permissions.add(permission)
            log = old.get_model("admin", "LogEntry").objects.create(
                user_id=user.pk,
                content_type_id=content_type.pk,
                object_id=str(user.pk),
                object_repr="existing",
                action_flag=1,
            )
            token = old.get_model("token_blacklist", "OutstandingToken").objects.create(
                user_id=user.pk,
                jti="existing-token",
                token="old-token",
                expires_at=timezone.now() + timedelta(days=1),
            )
            old.get_model("token_blacklist", "BlacklistedToken").objects.create(token_id=token.pk)
            old.get_model("sessions", "Session").objects.create(
                session_key="old-session",
                session_data="old-user-id",
                expire_date=timezone.now() + timedelta(days=1),
            )

            after = [("users", "0002_user_uuid")]
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            new = executor.loader.project_state(after).apps
            user = new.get_model("users", "User").objects.get(username="existing")
            self.assertIsInstance(user.pk, UUID)
            self.assertEqual(user.pk.version, 4)
            self.assertEqual(user.password, "preserve-this-hash")
            self.assertEqual(user.role, "OPERATIONS")
            self.assertEqual(list(user.groups.values_list("pk", flat=True)), [group.pk])
            self.assertEqual(
                list(user.user_permissions.values_list("pk", flat=True)), [permission.pk]
            )
            log = new.get_model("admin", "LogEntry").objects.get(pk=log.pk)
            self.assertEqual(log.user_id, user.pk)
            self.assertEqual(log.object_id, str(user.pk))
            token = new.get_model("token_blacklist", "OutstandingToken").objects.get(pk=token.pk)
            self.assertEqual(token.user_id, user.pk)
            self.assertTrue(new.get_model("token_blacklist", "BlacklistedToken").objects.exists())
            self.assertFalse(new.get_model("sessions", "Session").objects.exists())
            second = new.get_model("users", "User").objects.create(username="new")
            self.assertEqual(second.pk.version, 4)
            self.assertNotEqual(second.pk, user.pk)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('search_path', %s, false)", [original_path])
                cursor.execute(f"DROP SCHEMA {quote(schema)} CASCADE")
