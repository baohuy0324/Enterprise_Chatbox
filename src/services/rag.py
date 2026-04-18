import os
import tempfile
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_core.documents import Document
import pandas as pd
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from functools import lru_cache

import torch

@lru_cache(maxsize=1)
def get_embeddings():
    #Tạo Embeddings: Sử dụng HuggingFaceEmbeddings để không tải lại nhiều lần
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return HuggingFaceEmbeddings(
        model_name="all-MiniLM-L6-v2",
        model_kwargs={'device': device}
    )

def process_pdfs_to_vectorstore(pdf_files):
    #Chunking văn bản và tạo Vector database sử dụng FAISS.
    documents = []
    
    for filename, file_data in pdf_files:
        ext = filename.lower().split('.')[-1]
        
        # Tạo file tạm trên đĩa với đúng đuôi mở rộng
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp_file:
            temp_file.write(file_data.read())
            temp_path = temp_file.name
        
        try:
            # Route dựa trên đuôi file
            if ext == "pdf":
                loader = PyPDFLoader(temp_path)
                docs = loader.load()
            elif ext == "docx":
                loader = Docx2txtLoader(temp_path)
                docs = loader.load()
            elif ext == "xlsx":
                # Đọc ma trận Excel và ép nó thành dạng bảng text chay giả lập
                df = pd.read_excel(temp_path)
                text_content = df.to_string(index=False)
                docs = [Document(page_content=text_content, metadata={"source": temp_path, "page": 0})]
            else:
                docs = []
                
            # Gắn lại tên file thật vào metadata thay vì đường dẫn file tạm
            for doc in docs:
                doc.metadata["source"] = filename
            documents.extend(docs)
        finally:
            # Xoá file tạm khỏi hệ thống
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
    if not documents:
        return None
        
    # Chunking
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, # Giảm chunk size để chia nhỏ văn bản hơn, dễ lọc
        chunk_overlap=200, 
        separators=["\n\n", "\n", ".", "?", "!", " ", ""]  
    )
    chunks = text_splitter.split_documents(documents)
    
    # Khởi tạo vector store bằng FAISS
    vectorstore = FAISS.from_documents(chunks, get_embeddings())
    return vectorstore

def get_context(vectorstore, query: str, target_files: list[str] = None) -> str:
    """
    Thực hiện RAG: Áp dụng tìm kiếm đa dạng (Max Marginal Relevance) thay vì chỉ lấy độ giống.
    """
    if target_files:
        docs = vectorstore.max_marginal_relevance_search(
            query, 
            k=8, 
            fetch_k=40, 
            lambda_mult=0.1, 
            filter=lambda md: md.get("source") in target_files
        )
    else:
        docs = vectorstore.max_marginal_relevance_search(query, k=8, fetch_k=40, lambda_mult=0.1)
    
    # Gom nhóm theo nguồn để AI không bị loạn khi đọc nhiều file
    grouped_context = {}
    for doc in docs:
        source = doc.metadata.get("source", "Unknown file")
        page = doc.metadata.get("page", 0) + 1
        
        if source not in grouped_context:
            grouped_context[source] = []
        grouped_context[source].append(f"[Trang {page}]: {doc.page_content}")
        
    context_parts = []
    for source, chunks in grouped_context.items():
        chunk_text = "\n...\n".join(chunks)
        context_parts.append(f"BẮT ĐẦU NGUỒN: {source} \n{chunk_text}\n KẾT THÚC NGUỒN: {source}")
        
    context = "\n\n".join(context_parts)
    return context
