import os
import json
import chromadb
from sentence_transformers import SentenceTransformer


class LocalVectorStore:
    def __init__(self, username="default"):
        self.username = username
        self.persist_directory = f"data/vectorstore_{username}"
        os.makedirs(self.persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.client.get_or_create_collection(name=f"user_{username}")
        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )  # Lightweight embedding model

    def load_documents(self):
        # Load resume
        resume_path = "data/resume.txt"
        if os.path.exists(resume_path):
            with open(resume_path, "r") as f:
                resume_text = f.read()
            # Split into chunks
            chunks = [
                resume_text[i : i + 500] for i in range(0, len(resume_text), 450)
            ]  # Overlap
            if not self.collection.count():  # Only add if empty
                embeddings = self.model.encode(chunks)
                self.collection.add(
                    embeddings=embeddings.tolist(),
                    documents=chunks,
                    ids=[f"chunk_{i}" for i in range(len(chunks))],
                )
        else:
            print("Resume file not found. Please add data/resume.txt")

    def add_experience(self, experience_text):
        chunks = [
            experience_text[i : i + 500] for i in range(0, len(experience_text), 450)
        ]
        if chunks:
            embeddings = self.model.encode(chunks)
            ids = [f"exp_{self.collection.count() + i}" for i in range(len(chunks))]
            self.collection.add(
                embeddings=embeddings.tolist(), documents=chunks, ids=ids
            )

    def add_meeting_transcripts(self):
        # Load from transcript.txt
        transcript_path = "transcript.txt"
        if os.path.exists(transcript_path):
            with open(transcript_path, "r") as f:
                transcript_text = f.read()
            chunks = [
                transcript_text[i : i + 500]
                for i in range(0, len(transcript_text), 450)
            ]
            if chunks:
                embeddings = self.model.encode(chunks)
                ids = [
                    f"transcript_{self.collection.count() + i}"
                    for i in range(len(chunks))
                ]
                self.collection.add(
                    embeddings=embeddings.tolist(), documents=chunks, ids=ids
                )
        # Load from conversation_history.json
        history_path = "conversation_history.json"
        if os.path.exists(history_path):
            with open(history_path, "r") as f:
                history = json.load(f)
            history_text = " ".join(
                [
                    entry.get("transcript", "")
                    for entry in history
                    if "transcript" in entry
                ]
            )
            chunks = [
                history_text[i : i + 500] for i in range(0, len(history_text), 450)
            ]
            if chunks:
                embeddings = self.model.encode(chunks)
                ids = [
                    f"history_{self.collection.count() + i}" for i in range(len(chunks))
                ]
                self.collection.add(
                    embeddings=embeddings.tolist(), documents=chunks, ids=ids
                )

    def add_project_docs(self, docs_directory="docs"):
        if os.path.exists(docs_directory):
            for file in os.listdir(docs_directory):
                if file.endswith(".txt"):
                    with open(os.path.join(docs_directory, file), "r") as f:
                        doc_text = f.read()
                    chunks = [
                        doc_text[i : i + 500] for i in range(0, len(doc_text), 450)
                    ]
                    if chunks:
                        embeddings = self.model.encode(chunks)
                        ids = [
                            f"doc_{file}_{self.collection.count() + i}"
                            for i in range(len(chunks))
                        ]
                        self.collection.add(
                            embeddings=embeddings.tolist(), documents=chunks, ids=ids
                        )

    def add_user_preferences(self):
        # Load from user_preferences.txt (user-defined preferences or notes)
        prefs_path = "data/user_preferences.txt"
        if os.path.exists(prefs_path):
            with open(prefs_path, "r") as f:
                prefs_text = f.read()
            chunks = [prefs_text[i : i + 500] for i in range(0, len(prefs_text), 450)]
            if chunks:
                embeddings = self.model.encode(chunks)
                ids = [
                    f"prefs_{self.collection.count() + i}" for i in range(len(chunks))
                ]
                self.collection.add(
                    embeddings=embeddings.tolist(), documents=chunks, ids=ids
                )
        else:
            print(
                "User preferences file not found. Create data/user_preferences.txt for custom context."
            )

    def search(self, query, k=3):
        query_embedding = self.model.encode([query]).tolist()
        results = self.collection.query(query_embeddings=query_embedding, n_results=k)
        # Return as dict
        return [{"page_content": doc} for doc in results["documents"][0]]


if __name__ == "__main__":
    store = LocalVectorStore()
    store.load_documents()
    # Test search
    results = store.search("project management")
    for doc in results:
        print(doc.page_content)
