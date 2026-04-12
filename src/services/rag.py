import os
import tempfile
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from functools import lru_cache

import torch

@lru_cache(maxsize=1)
def get_embeddings():
    """Tạo Embeddings: Sử dụng HuggingFaceEmbeddings (Local) để không tải lại nhiều lần"""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return HuggingFaceEmbeddings(
        model_name="all-MiniLM-L6-v2",
        model_kwargs={'device': device}
    )

def process_pdfs_to_vectorstore(pdf_files):
    """
    Chunking văn bản và tạo Vector database sử dụng FAISS.
    """
    documents = []
    
    for pdf in pdf_files:
        # Pypdfloader cần một path trỏ tới file thực, tạo một file tạm trên đĩa
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf.read())
            temp_path = temp_file.name
        
        try:
            # Load văn bản
            loader = PyPDFLoader(temp_path)
            docs = loader.load()
            documents.extend(docs)
        finally:
            # Xoá file tạm khỏi hệ thống
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
    if not documents:
        return None
        
    # Chunking
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500, # Chunk lớn hơn để ôm trọn ý đoạn văn
        chunk_overlap=300, # Trùng lặp sâu hơn để khỏi đứt đoạn câu chi tiết
        separators=["\n\n", "\n", ".", "?", "!", " ", ""]  
    )
    chunks = text_splitter.split_documents(documents)
    
    # Khởi tạo vector store bằng FAISS
    vectorstore = FAISS.from_documents(chunks, get_embeddings())
    return vectorstore

def get_context(vectorstore, query: str) -> str:
    """
    Thực hiện RAG: Áp dụng tìm kiếm đa dạng (Max Marginal Relevance) thay vì chỉ lấy độ giống.
    Rất hiệu quả cho các câu hỏi tổng quát. Tăng view lên k=6 chunk đa dạng.
    """
    docs = vectorstore.max_marginal_relevance_search(query, k=6, fetch_k=20)
    context = "\n\n".join([doc.page_content for doc in docs])
    return context
