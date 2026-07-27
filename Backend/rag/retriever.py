import os
from typing import List, Dict, Any
from langchain_community.document_loaders import DirectoryLoader, UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from loguru import logger

RAG_DATA_DIR = os.path.join(os.path.dirname(__file__), "legal_data")
CHROMA_DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")

class LegalRetriever:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(model_name="keepitreal/vietnamese-sbert")
        self.vector_store = None
        self._init_vector_store()

    def _init_vector_store(self):
        if os.path.exists(CHROMA_DB_DIR) and os.listdir(CHROMA_DB_DIR):
            logger.info("Loading existing ChromaDB from disk.")
            self.vector_store = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=self.embeddings)
        else:
            logger.info("ChromaDB not found. Initializing from markdown files...")
            self.vector_store = self._build_index()

    def _build_index(self):
        if not os.path.exists(RAG_DATA_DIR):
            os.makedirs(RAG_DATA_DIR, exist_ok=True)
            logger.warning(f"RAG Data directory created at {RAG_DATA_DIR}. Please add .md files here.")
            return Chroma.from_texts(["Dữ liệu pháp lý trống."], self.embeddings, persist_directory=CHROMA_DB_DIR)

        loader = DirectoryLoader(RAG_DATA_DIR, glob="**/*.md", loader_cls=UnstructuredMarkdownLoader)
        docs = loader.load()

        if not docs:
            logger.warning("No markdown documents found for RAG.")
            return Chroma.from_texts(["Dữ liệu pháp lý trống."], self.embeddings, persist_directory=CHROMA_DB_DIR)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)

        vector_store = Chroma.from_documents(documents=splits, embedding=self.embeddings, persist_directory=CHROMA_DB_DIR)
        logger.success(f"Built ChromaDB index with {len(splits)} chunks.")
        return vector_store

    def retrieve(self, query: str, k: int = 3) -> str:
        if not self.vector_store:
            return ""
        results = self.vector_store.similarity_search(query, k=k)
        context = "\n\n".join([doc.page_content for doc in results])
        return context

# Singleton instance
retriever_instance = LegalRetriever()

def get_legal_context(query: str) -> str:
    return retriever_instance.retrieve(query)
