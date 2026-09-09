# Project conventions

- Use UUIDv4 primary keys for all application-owned domain models:
  `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`.
- Represent IDs as UUID strings in API responses and OpenAPI schemas. Use Django's
  `<uuid:pk>` converter for future object-detail routes.
- Keep Django and third-party internal primary keys unchanged. Foreign keys to
  application models must use the corresponding UUID type.
- Preserve existing records when changing schemas. Do not reset the database or
  rewrite applied migrations to simplify a change.
