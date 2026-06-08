import chromadb
import sqlite3

def test_recover():
    persist_dir = "./data/chroma_db"
    
    # Get IDs directly from SQLite
    c = sqlite3.connect(f'{persist_dir}/chroma.sqlite3')
    ids = [r[0] for r in c.execute("SELECT embedding_id FROM embeddings").fetchall()]
    print(f"Found {len(ids)} total IDs in SQLite.")
    
    client = chromadb.PersistentClient(path=persist_dir)
    col = client.get_collection("legal_documents_multilingual_v2")
    
    success = 0
    failed = 0
    
    for i in range(0, len(ids), 100):
        batch = ids[i:i+100]
        try:
            data = col.get(ids=batch, include=["embeddings", "metadatas", "documents"])
            success += len(data["ids"])
        except Exception as e:
            failed += len(batch)
            
    print(f"Recovered {success} complete records. Failed on {failed} records.")

if __name__ == "__main__":
    test_recover()
