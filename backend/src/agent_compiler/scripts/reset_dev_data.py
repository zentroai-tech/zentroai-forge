"""Reset development database data for v2-only workflows.

This script drops and recreates all SQLModel tables using current metadata.
Use only in local/dev environments.
"""

import asyncio

from sqlmodel import SQLModel

from agent_compiler.database import get_engine


async def reset_dev_data() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    print("Development database reset complete (all tables recreated).")


if __name__ == "__main__":
    asyncio.run(reset_dev_data())

