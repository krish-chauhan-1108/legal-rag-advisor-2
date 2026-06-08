import sqlite3

def optimize_fts():
    print("Connecting to DB...")
    c = sqlite3.connect('data/chroma_db/chroma.sqlite3')
    
    print("Running FTS5 optimization...")
    c.execute("INSERT INTO embedding_fulltext_search(embedding_fulltext_search) VALUES('optimize')")
    c.commit()
    
    print("Running VACUUM...")
    c.execute("VACUUM")
    c.commit()
    
    c.close()
    
    import os
    size = os.path.getsize('data/chroma_db/chroma.sqlite3') / 1024 / 1024
    print(f"Optimization complete. New DB size: {size:.2f} MB")

if __name__ == "__main__":
    optimize_fts()
