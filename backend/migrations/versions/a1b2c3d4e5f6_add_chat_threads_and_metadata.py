"""add chat threads and metadata

Revision ID: a1b2c3d4e5f6
Revises: 0221e365797d
Create Date: 2026-09-17 02:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0221e365797d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_threads',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('classroom_id', sa.String(length=36), nullable=False),
        sa.Column('class_session_id', sa.String(length=36), nullable=True),
        sa.Column('experiment_id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False, server_default='New chat'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['classroom_id'], ['classrooms.id']),
        sa.ForeignKeyConstraint(['class_session_id'], ['class_sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_threads_user_id'), 'chat_threads', ['user_id'], unique=False)
    op.create_index(op.f('ix_chat_threads_classroom_id'), 'chat_threads', ['classroom_id'], unique=False)
    op.create_index(op.f('ix_chat_threads_class_session_id'), 'chat_threads', ['class_session_id'], unique=False)
    op.create_index(op.f('ix_chat_threads_experiment_id'), 'chat_threads', ['experiment_id'], unique=False)

    with op.batch_alter_table('chat_messages') as batch_op:
        batch_op.add_column(sa.Column('thread_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('metadata_json', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.alter_column('kind', type_=sa.Enum('SOCRATIC', 'QA', 'DIAGNOSTIC', name='chatmessagekind'), existing_type=sa.Enum('SOCRATIC', 'QA', name='chatmessagekind'))
        batch_op.create_foreign_key('fk_chat_messages_thread_id', 'chat_threads', ['thread_id'], ['id'])
        batch_op.create_index(op.f('ix_chat_messages_thread_id'), ['thread_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('chat_messages') as batch_op:
        batch_op.drop_index(op.f('ix_chat_messages_thread_id'))
        batch_op.drop_constraint('fk_chat_messages_thread_id', type_='foreignkey')
        batch_op.alter_column('kind', type_=sa.Enum('SOCRATIC', 'QA', name='chatmessagekind'), existing_type=sa.Enum('SOCRATIC', 'QA', 'DIAGNOSTIC', name='chatmessagekind'))
        batch_op.drop_column('metadata_json')
        batch_op.drop_column('thread_id')
    op.drop_index(op.f('ix_chat_threads_experiment_id'), table_name='chat_threads')
    op.drop_index(op.f('ix_chat_threads_class_session_id'), table_name='chat_threads')
    op.drop_index(op.f('ix_chat_threads_classroom_id'), table_name='chat_threads')
    op.drop_index(op.f('ix_chat_threads_user_id'), table_name='chat_threads')
    op.drop_table('chat_threads')
