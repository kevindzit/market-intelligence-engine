import os
import chromadb
import re
from crewai import Agent, Task, Crew, Process
from langchain_ollama import OllamaLLM

# --- Configuration ---
CHROMA_PATH = "chroma_db_news"
COLLECTION_NAME = "news_articles"

# --- Initialize ChromaDB Client ---
try:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)
    print(f"Successfully connected to ChromaDB. Articles in collection: {collection.count()}")
except Exception as e:
    print(f"Error connecting to ChromaDB: {e}")
    exit()

# --- Initialize the Local AI Model ---
ollama_phi3 = OllamaLLM(model="ollama/phi3:mini", base_url="http://localhost:11434")
print("Ollama model (phi3:mini) initialized.")

# --- Define the Agents ---
news_triage_agent = Agent(
    role='Financial News Triage Specialist',
    goal='Analyze a list of recent financial news headlines and classify each one as either "Investigate" or "Ignore".',
    backstory=(
        "You are an expert at quickly identifying market-moving news. "
        "Your strength is in rapidly scanning headlines to filter out irrelevant information, "
        "allowing your team to focus only on what truly matters. You are fast, efficient, and have a sharp eye for impactful events."
    ),
    verbose=True,
    allow_delegation=False,
    llm=ollama_phi3
)
print("News Triage Agent created.")

# --- Define the Tasks ---
def get_latest_news_from_db(num_articles=25):
    """Fetches the most recent articles from the ChromaDB collection."""
    try:
        results = collection.get(
            include=['metadatas', 'documents'],
            limit=num_articles
        )
        return results
    except Exception as e:
        print(f"Error fetching news from ChromaDB: {e}")
        return None

latest_news = get_latest_news_from_db()

def format_news_for_llm(news_data):
    """Formats the news data into a string for the AI to read."""
    if not news_data or not news_data.get('metadatas'):
        return "No new articles found."
    
    formatted_news = ""
    for i, metadata in enumerate(news_data['metadatas']):
        headline = metadata.get('headline', 'No Headline')
        snippet = news_data['documents'][i] if news_data.get('documents') else 'No Snippet'
        formatted_news += f"Item {i+1}:\nHeadline: {headline}\nSnippet: {snippet}\n\n"
    return formatted_news

# --- IMPROVED PROMPT AND EXPECTED OUTPUT ---
triage_task = Task(
    description=(
        "Analyze each of the following news items and classify them. Your answer for each item MUST be either 'Investigate' or 'Ignore'. "
        "An item is 'Investigate' if it is likely market-moving (major earnings, M&A, Fed news, economic data, geopolitical events, CEO changes). "
        "An item is 'Ignore' if it is general commentary, opinion, or clearly non-financial.\n\n"
        "--- LATEST NEWS ---\n"
        f"{format_news_for_llm(latest_news)}"
    ),
    expected_output=(
        "A numbered list where each line contains ONLY the word 'Investigate' or 'Ignore'. Do not add any extra commentary or reasoning. "
        "For example:\n"
        "1. Investigate\n"
        "2. Ignore\n"
        "3. Investigate"
    ),
    agent=news_triage_agent
)
print("News Triage Task created.")

# --- Create and Run the Crew ---
news_crew = Crew(
    agents=[news_triage_agent],
    tasks=[triage_task],
    process=Process.sequential,
    verbose=True 
)

print("\n--- Kicking off the News Triage Crew ---")
result = news_crew.kickoff()

print("\n--- Triage Crew Finished ---")
print("Final Raw Result from Triage Agent:")
print(result.raw)

# --- IMPROVED PROCESSING OF THE TRIAGE RESULT ---
if result and result.raw:
    # Use regex to find all occurrences of "Investigate" or "Ignore"
    classifications = re.findall(r'(Investigate|Ignore)', result.raw)
    
    print("\n--- Extracted Classifications ---")
    investigate_list = []
    
    if len(classifications) == 0:
        print("Agent did not return any valid classifications.")
    else:
        for i, classification in enumerate(classifications):
            # Ensure we don't go out of bounds of the news list
            if latest_news and len(latest_news['ids']) > i:
                if 'Investigate' in classification:
                    news_item = {
                        'headline': latest_news['metadatas'][i].get('headline'),
                        'url': latest_news['ids'][i]
                    }
                    investigate_list.append(news_item)
                    print(f"Item {i+1}: {classification} -> Will be researched.")
                else:
                    print(f"Item {i+1}: {classification} -> Ignoring.")
            else:
                break # Stop if classifications exceed number of news items

    print("\n--- Headlines to be Researched by the Next Agent ---")
    if investigate_list:
        for item in investigate_list:
            print(f"- {item['headline']}")
    else:
        print("No significant news to investigate further.")

