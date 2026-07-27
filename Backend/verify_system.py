import asyncio
import os
from loguru import logger
from database.models import engine
from z3 import Solver, Int, sat
from rag.retriever import RAG_DATA_DIR, CHROMA_DB_DIR, retriever_instance

async def check_postgres():
    try:
        async with engine.connect() as conn:
            # Chạy thử một kết nối
            pass
        logger.success("[PASS] PostgreSQL Database connection successful.")
    except Exception as e:
        logger.error(f"[FAIL] PostgreSQL Database connection failed: {e}")

def check_z3():
    try:
        s = Solver()
        x = Int('x')
        s.add(x + 1 == 2)
        if s.check() == sat:
            logger.success("[PASS] Z3 Solver is working properly.")
        else:
            logger.error("[FAIL] Z3 Solver failed basic arithmetic.")
    except Exception as e:
        logger.error(f"[FAIL] Z3 Solver exception: {e}")

def check_rag():
    try:
        if not os.path.exists(RAG_DATA_DIR) or not os.listdir(RAG_DATA_DIR):
            logger.warning("[WARNING] RAG data directory is empty or missing.")
        else:
            logger.success(f"[PASS] RAG data directory exists with files: {os.listdir(RAG_DATA_DIR)}")
        
        if retriever_instance.vector_store is not None:
            logger.success("[PASS] ChromaDB initialized successfully.")
        else:
            logger.error("[FAIL] ChromaDB failed to initialize.")
    except Exception as e:
        logger.error(f"[FAIL] RAG check exception: {e}")

async def main():
    logger.info("=========================================")
    logger.info("   TRUSTAGENT E2E DIAGNOSTIC TOOL")
    logger.info("=========================================")
    await check_postgres()
    check_z3()
    check_rag()
    logger.info("Diagnostics completed.")

if __name__ == "__main__":
    asyncio.run(main())
