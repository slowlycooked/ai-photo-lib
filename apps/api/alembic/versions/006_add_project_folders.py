"""
Alembic migration for project_folders table and photos table folder fields

Revision ID: 006_add_project_folders
Revises: 005_add_exif_fields_and_ai_project
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = '006_add_project_folders'
down_revision = '005'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'project_folders',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('project_id', sa.BigInteger(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_id', sa.BigInteger(), sa.ForeignKey('project_folders.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('relative_path', sa.Text(), nullable=False),
        sa.Column('depth', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('photo_count_direct', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('photo_count_recursive', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('project_id', 'relative_path', name='uq_project_folders_project_path'),
    )
    op.create_index('ix_project_folders_project_parent', 'project_folders', ['project_id', 'parent_id'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('ix_project_folders_project_path', 'project_folders', ['project_id', 'relative_path'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))

    op.add_column('photos', sa.Column('folder_id', sa.BigInteger(), sa.ForeignKey('project_folders.id', ondelete='SET NULL'), nullable=True))
    op.add_column('photos', sa.Column('relative_path', sa.Text(), nullable=True))
    op.add_column('photos', sa.Column('folder_path', sa.Text(), nullable=True))
    op.create_index('ix_photos_project_folder', 'photos', ['project_id', 'folder_id'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('ix_photos_project_folder_taken_at', 'photos', ['project_id', 'folder_id', 'taken_at'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))

def downgrade():
    op.drop_index('ix_photos_project_folder_taken_at', table_name='photos')
    op.drop_index('ix_photos_project_folder', table_name='photos')
    op.drop_column('photos', 'folder_path')
    op.drop_column('photos', 'relative_path')
    op.drop_column('photos', 'folder_id')
    op.drop_index('ix_project_folders_project_path', table_name='project_folders')
    op.drop_index('ix_project_folders_project_parent', table_name='project_folders')
    op.drop_table('project_folders')
