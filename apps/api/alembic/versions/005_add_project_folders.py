"""
No-op marker revision after the project folder schema migration.
"""

revision = '007_add_project_folders'
down_revision = '006_merge_005_heads'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
