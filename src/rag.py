import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# 本地模型路径
EMBEDDING_MODEL_PATH = os.path.abspath("../model/embedding/paraphrase-multilingual-MiniLM-L12-v2")


# 初始化向量库
def init_vectorstore(docuPath:str):
    loader = TextLoader(docuPath, encoding="utf-8")
    docs = loader.load()

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("##", "action_name")],
        strip_headers=False
    )
    md_header_splits = markdown_splitter.split_text(docs[0].page_content)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", " "]
    )
    splits = text_splitter.split_documents(md_header_splits)

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_PATH
    )
    vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings)
    return vectorstore.as_retriever()