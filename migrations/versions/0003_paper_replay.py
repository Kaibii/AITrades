"""Durable virtual paper portfolios, order journal, risk events and worker heartbeat."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    money = sa.Numeric(38, 18)
    op.create_table(
        "paper_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("strategy_drafts.id"), nullable=False),
        sa.Column("backtest_id", sa.String(36), sa.ForeignKey("backtest_runs.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_tick_at", sa.DateTime(timezone=True)),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("specification", sa.JSON(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("bars", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        *(
            sa.Column(name, money, nullable=False)
            for name in ("cash", "quantity", "equity", "peak_equity")
        ),
    )
    op.create_table(
        "paper_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("paper_sessions.id"), nullable=False),
        sa.Column("client_order_id", sa.String(48), unique=True, nullable=False),
        sa.Column("bar_index", sa.Integer(), nullable=False),
        sa.Column("market_date", sa.String(10), nullable=False),
        sa.Column("symbol", sa.String(10), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("quantity", money, nullable=False),
        sa.Column("filled_quantity", money, nullable=False),
        sa.Column("fill_price", money),
        sa.Column("fee", money, nullable=False),
        sa.Column("reason", sa.Text()),
        sa.UniqueConstraint("session_id", "bar_index", "side", name="uq_paper_signal"),
    )
    op.create_index("ix_paper_orders_session_id", "paper_orders", ["session_id"])
    op.create_table(
        "paper_risk_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("paper_sessions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_date", sa.String(10)),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_paper_risk_events_session_id", "paper_risk_events", ["session_id"])
    op.create_table(
        "paper_worker_heartbeats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for table in ("paper_worker_heartbeats", "paper_risk_events", "paper_orders", "paper_sessions"):
        op.drop_table(table)
