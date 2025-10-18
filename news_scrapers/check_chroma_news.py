import chromadb
import os

# --- Configuration (Should match your reader script) ---
CHROMA_PATH = "chroma_db_news" # Folder where ChromaDB stores data
COLLECTION_NAME = "news_articles"

print(f"--- Checking ChromaDB Collection: '{COLLECTION_NAME}' ---")

if not os.path.exists(CHROMA_PATH):
    print(f"Error: ChromaDB path '{CHROMA_PATH}' not found.")
else:
    try:
        # Connect to the existing persistent client
        chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

        # Get the collection
        try:
            collection = chroma_client.get_collection(name=COLLECTION_NAME)
            print(f"Successfully connected to collection '{COLLECTION_NAME}'.")

            # Get the count of items
            count = collection.count()
            print(f"Total articles in collection: {count}")

            # Get the 5 most recent items (or fewer if less than 5 exist)
            if count > 0:
                print("\n--- Last 5 Stored Articles (approx.) ---")
                results = collection.get(
                    include=['metadatas', 'documents'], # Get metadata and the stored text
                    limit=min(100, count) # Limit to 5 or the total count
                    # Note: Chroma doesn't inherently store in time order unless specified,
                    # this just gets *some* recent entries based on internal storage.
                )

                if results and results.get('ids'):
                    for i in range(len(results['ids'])):
                        doc_id = results['ids'][i]
                        metadata = results['metadatas'][i] if results['metadatas'] else {}
                        document = results['documents'][i] if results['documents'] else "N/A"

                        print(f"\nArticle ID (URL): {doc_id}")
                        print(f"  Headline: {metadata.get('headline', 'N/A')}")
                        print(f"  Source: {metadata.get('source', 'N/A')}")
                        print(f"  Published: {metadata.get('timestamp', 'N/A')}")
                        print(f"  Stored Text Snippet: {document[:150]}...") # Show beginning of text
                else:
                    print("Could not retrieve articles.")
            else:
                print("Collection is empty.")

        except Exception as e:
            print(f"Error getting collection '{COLLECTION_NAME}': {e}")
            print("Maybe the collection name is wrong, or the database is corrupted?")

    except Exception as e:
        print(f"Error connecting to ChromaDB client at '{CHROMA_PATH}': {e}")

print("\n--- Check Complete ---")