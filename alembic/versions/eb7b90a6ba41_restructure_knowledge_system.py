# alembic/versions/eb7b90a6ba41_restructure_knowledge_system.py
"""
Restructure knowledge system: Create services, documents, document_chunks tables
and migrate existing BusinessKnowledge data.

Revision ID: eb7b90a6ba41
Revises: 77ac24ed6689
Create Date: 2024-01-XX XX:XX:XX.XXXXXX
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text
import uuid
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'eb7b90a6ba41'
down_revision = '77ac24ed6689'
branch_labels = None
depends_on = None

# Mapping from old categories to new document types
CATEGORY_TO_DOCTYPE = {
    'service_info': 'general',
    'pricing': 'general',
    'policies': 'policy',
    'faq': 'faq',
    'business_hours': 'general',
    'contact_info': 'general',
    'general': 'general',
}


def upgrade():
    """
    Upgrade: Create new tables and migrate existing data
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ========================================================================
    # STEP 1: Create Enum Types (idempotent with raw SQL)
    # ========================================================================

    bind.execute(text("""
        DO $$ BEGIN
            CREATE TYPE document_type AS ENUM ('pdf', 'note', 'policy', 'faq', 'guide', 'general');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))

    bind.execute(text("""
        DO $$ BEGIN
            CREATE TYPE indexing_status AS ENUM ('pending', 'processing', 'complete', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))

    # Now define enum objects for SQLAlchemy, but don't let them auto-create
    document_type_enum = postgresql.ENUM(
        'pdf', 'note', 'policy', 'faq', 'guide', 'general',
        name='document_type',
        create_type=False  # CRITICAL: Don't auto-create
    )

    indexing_status_enum = postgresql.ENUM(
        'pending', 'processing', 'complete', 'failed',
        name='indexing_status',
        create_type=False  # CRITICAL: Don't auto-create
    )

    # ========================================================================
    # STEP 2: Create Services Table
    # ========================================================================
    if not inspector.has_table("services"):
        op.create_table(
            'services',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('price', sa.Numeric(10, 2), nullable=True),
            sa.Column('price_display', sa.String(50), nullable=True),
            sa.Column('duration', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_services_business_id', 'services', ['business_id'])
        op.create_index('ix_services_is_active', 'services', ['is_active'])

    # ========================================================================
    # STEP 3: Create Documents Table
    # ========================================================================
    if not inspector.has_table("documents"):
        op.create_table(
            'documents',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('type', document_type_enum, nullable=False),
            sa.Column('original_content', sa.Text(), nullable=False),
            sa.Column('file_path', sa.String(1000), nullable=True),
            sa.Column('original_filename', sa.String(500), nullable=True),
            sa.Column('file_size', sa.BigInteger(), nullable=True),
            sa.Column('indexing_status', indexing_status_enum, nullable=False, server_default='complete'),
            sa.Column('indexing_error', sa.Text(), nullable=True),
            sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('related_service_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('previous_version_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['related_service_id'], ['services.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['previous_version_id'], ['documents.id'], ondelete='SET NULL'),
        )
        op.create_index('ix_documents_business_id', 'documents', ['business_id'])
        op.create_index('ix_documents_type', 'documents', ['type'])
        op.create_index('ix_documents_indexing_status', 'documents', ['indexing_status'])
        op.create_index('ix_documents_related_service_id', 'documents', ['related_service_id'])
        op.create_index('ix_documents_is_active', 'documents', ['is_active'])

    # ========================================================================
    # STEP 4: Create DocumentChunks Table
    # ========================================================================
    if not inspector.has_table("document_chunks"):
        op.create_table(
            'document_chunks',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=False),  # Will be Vector type
            sa.Column('chunk_index', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('extra_metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_document_chunks_document_id', 'document_chunks', ['document_id'])
        op.create_index('ix_document_chunks_is_active', 'document_chunks', ['is_active'])

    # ========================================================================
    # STEP 5: Migrate Data from business_knowledge to documents/document_chunks
    # ========================================================================

    print("Starting data migration from business_knowledge...")

    # Get all business_knowledge records grouped by business_id and category
    result = bind.execute(text("""
        SELECT 
            business_id,
            category,
            COUNT(*) as chunk_count,
            MIN(created_at) as earliest_created
        FROM business_knowledge
        WHERE is_active = true
        GROUP BY business_id, category
        ORDER BY business_id, category
    """))

    knowledge_groups = result.fetchall()
    print(f"Found {len(knowledge_groups)} knowledge groups to migrate")

    # For each group, create a document and migrate chunks
    for group in knowledge_groups:
        business_id = group[0]
        category = group[1]
        chunk_count = group[2]
        created_at = group[3]

        # Map category to document type
        doc_type = CATEGORY_TO_DOCTYPE.get(category, 'general')

        # Create a document for this group
        document_id = str(uuid.uuid4())
        doc_title = f"Migrated {category.replace('_', ' ').title()} Knowledge"

        bind.execute(text("""
            INSERT INTO documents (
                id, business_id, title, type, original_content,
                indexing_status, indexed_at, is_active, created_at, updated_at
            )
            VALUES (
                :id, :business_id, :title, :type, :content,
                'complete', :indexed_at, true, :created_at, :updated_at
            )
        """), {
            'id': document_id,
            'business_id': business_id,
            'title': doc_title,
            'type': doc_type,
            'content': f"Migrated from business_knowledge table (category: {category})",
            'indexed_at': created_at,
            'created_at': created_at,
            'updated_at': created_at
        })

        # Migrate all chunks for this group
        bind.execute(text("""
            INSERT INTO document_chunks (
                id, document_id, content, embedding, chunk_index,
                extra_metadata, is_active, created_at, updated_at
            )
            SELECT 
                gen_random_uuid(),
                :document_id,
                content,
                embedding::double precision[],
                chunk_index,
                jsonb_build_object(
                    'migrated_from', 'business_knowledge',
                    'original_category', category::text,
                    'source_field', source_field,
                    'original_metadata', extra_metadata
                ),
                is_active,
                created_at,
                updated_at
            FROM business_knowledge
            WHERE business_id = :business_id 
              AND category = :category
              AND is_active = true
        """), {
            'document_id': document_id,
            'business_id': business_id,
            'category': category
        })

        print(f"  Migrated {chunk_count} chunks for business {business_id}, category {category}")

    print("Data migration from business_knowledge completed!")

    # ========================================================================
    # STEP 6: Migrate Services from businesses.service_catalog JSON
    # ========================================================================

    print("Starting migration of services from businesses.service_catalog...")

    # Get all businesses with service_catalog data
    result = bind.execute(text("""
        SELECT id, service_catalog, services
        FROM businesses
        WHERE service_catalog IS NOT NULL 
           OR services IS NOT NULL
    """))

    businesses = result.fetchall()
    print(f"Found {len(businesses)} businesses with service data")

    for business in businesses:
        business_id = business[0]
        service_catalog = business[1] or {}
        services_json = business[2] or []

        # Handle both service_catalog (dict) and services (list) formats
        services_to_migrate = []

        # If service_catalog is a dict with service entries
        if isinstance(service_catalog, dict):
            for service_name, service_data in service_catalog.items():
                if isinstance(service_data, dict):
                    services_to_migrate.append({
                        'name': service_name,
                        **service_data
                    })

        # If services is a list
        if isinstance(services_json, list):
            for service in services_json:
                if isinstance(service, dict) and 'name' in service:
                    services_to_migrate.append(service)

        # Insert services
        for idx, service in enumerate(services_to_migrate):
            service_id = str(uuid.uuid4())

            # Extract price (handle various formats)
            price = None
            price_display = None
            if 'price' in service:
                if isinstance(service['price'], (int, float)):
                    price = float(service['price'])
                else:
                    price_display = str(service['price'])

            # Extract duration (convert to minutes if needed)
            duration = None
            if 'duration' in service:
                duration = service.get('duration')
                if isinstance(duration, str):
                    # Try to parse duration strings like "30m", "1h", etc.
                    duration_str = duration.lower()
                    if 'h' in duration_str:
                        hours = float(duration_str.replace('h', '').strip())
                        duration = int(hours * 60)
                    elif 'm' in duration_str:
                        duration = int(duration_str.replace('m', '').strip())

            bind.execute(text("""
                INSERT INTO services (
                    id, business_id, name, description, price, price_display,
                    duration, is_active, display_order, created_at, updated_at
                )
                VALUES (
                    :id, :business_id, :name, :description, :price, :price_display,
                    :duration, :is_active, :display_order, NOW(), NOW()
                )
            """), {
                'id': service_id,
                'business_id': business_id,
                'name': service.get('name', 'Unnamed Service'),
                'description': service.get('description'),
                'price': price,
                'price_display': price_display,
                'duration': duration,
                'is_active': service.get('is_active', True),
                'display_order': idx
            })

        if services_to_migrate:
            print(f"  Migrated {len(services_to_migrate)} services for business {business_id}")

    print("Service migration completed!")

    # ========================================================================
    # STEP 7: Rename business_knowledge table to mark as deprecated
    # ========================================================================

    print("Renaming business_knowledge table to business_knowledge_deprecated...")
    bind.execute(text("""
        ALTER TABLE business_knowledge 
        RENAME TO business_knowledge_deprecated
    """))

    # Also rename the indexes
    bind.execute(text("""
        ALTER INDEX business_knowledge_pkey 
        RENAME TO business_knowledge_deprecated_pkey
    """))
    bind.execute(text("""
        ALTER INDEX ix_business_knowledge_business_id 
        RENAME TO ix_business_knowledge_deprecated_business_id
    """))
    bind.execute(text("""
        ALTER INDEX ix_business_knowledge_category 
        RENAME TO ix_business_knowledge_deprecated_category
    """))
    bind.execute(text("""
        ALTER INDEX ix_business_knowledge_is_active 
        RENAME TO ix_business_knowledge_deprecated_is_active
    """))

    print("Migration completed successfully!")
    print("=" * 80)
    print("SUMMARY:")
    print(f"  - Created tables: services, documents, document_chunks")
    print(f"  - Migrated business_knowledge → documents/document_chunks")
    print(f"  - Migrated businesses.service_catalog → services")
    print(f"  - Renamed business_knowledge → business_knowledge_deprecated")
    print("=" * 80)


def downgrade():
    """
    Downgrade: Restore business_knowledge table and drop new tables
    """
    bind = op.get_bind()

    # Restore business_knowledge table name
    bind.execute(text("""
        ALTER TABLE IF EXISTS business_knowledge_deprecated 
        RENAME TO business_knowledge
    """))

    # Restore index names
    bind.execute(text("""
        ALTER INDEX IF EXISTS business_knowledge_deprecated_pkey 
        RENAME TO business_knowledge_pkey
    """))
    bind.execute(text("""
        ALTER INDEX IF EXISTS ix_business_knowledge_deprecated_business_id 
        RENAME TO ix_business_knowledge_business_id
    """))
    bind.execute(text("""
        ALTER INDEX IF EXISTS ix_business_knowledge_deprecated_category 
        RENAME TO ix_business_knowledge_category
    """))
    bind.execute(text("""
        ALTER INDEX IF EXISTS ix_business_knowledge_deprecated_is_active 
        RENAME TO ix_business_knowledge_is_active
    """))

    # Drop new tables (cascades will handle foreign keys)
    op.execute('DROP TABLE IF EXISTS document_chunks CASCADE')
    op.execute('DROP TABLE IF EXISTS documents CASCADE')
    op.execute('DROP TABLE IF EXISTS services CASCADE')

    # Drop ENUM types
    op.execute('DROP TYPE IF EXISTS document_type')
    op.execute('DROP TYPE IF EXISTS indexing_status')