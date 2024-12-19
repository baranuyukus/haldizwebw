"""add num_points and shape fields to project

Revision ID: ec9486ff7e6d
Revises: 4d6c935eb920
Create Date: 2024-12-18 20:34:14.015173

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ec9486ff7e6d'
down_revision = '4d6c935eb920'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(sa.Column('num_points', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('shape', sa.String(length=20), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_column('shape')
        batch_op.drop_column('num_points')

    # ### end Alembic commands ###