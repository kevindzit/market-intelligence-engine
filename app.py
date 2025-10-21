import os
import chromadb
from crewai import Agent, Task, Crew, Process
# Import the correctly named class 'OllamaLLM'
from langchain_ollama import OllamaLLM 

# --- Configuration ---
# Set up the folder for the ChromaDB database
CHROMA_PATH = "chroma_db_news"
COLLECTION_NAME = "news_articles"

# --- Setup Logging ---
# (Optional for now, can add later if needed)

# --- Initialize ChromaDB Client ---
# This connects to the same database your news scrapers are writing to.
try:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)
    print(f"Successfully connected to ChromaDB. Articles in collection: {collection.count()}")
except Exception as e:
    print(f"Error connecting to ChromaDB: {e}")
    exit()

# --- Initialize the Local AI Model ---
# This tells CrewAI to use your local Ollama instance with the phi3:mini model.
# *** CHANGE: Explicitly name the provider in the model string for litellm. ***
ollama_phi3 = OllamaLLM(model="ollama/phi3:mini", base_url="http://localhost:11434")
print("Ollama model (phi3:mini) initialized.")

# --- Define the Agents ---

# Agent 1: The News Triage Agent
# This agent's only job is to quickly read headlines and decide if they are important.
news_triage_agent = Agent(
    role='Financial News Triage Specialist',
    goal='Analyze a list of recent financial news headlines and snippets, and classify each one as either "Significant" or "Noise".',
    backstory=(
        "You are an expert at quickly identifying market-moving news. "
        "Your strength is in rapidly scanning headlines to filter out irrelevant information, "
        "allowing your team to focus only on what truly matters. You are fast, efficient, and have a sharp eye for impactful events."
    ),
    verbose=True,
    allow_delegation=False,
    llm=ollama_phi3 # Use the small, fast model
)
print("News Triage Agent created.")

# --- Define the Tasks ---

# Task 1: Triage the Latest News
def get_latest_news_from_db(num_articles=25):
    """Fetches the most recent articles from the ChromaDB collection."""
    try:
        results = collection.get(
            include=['metadatas', 'documents'],
            limit=num_articles
        )
        
        # Format the news into a simple string for the AI to read
        formatted_news = ""
        for i, metadata in enumerate(results.get('metadatas', [])):
            headline = metadata.get('headline', 'No Headline')
            snippet = results['documents'][i] if results.get('documents') else 'No Snippet'
            formatted_news += f"Item {i+1}:\nHeadline: {headline}\nSnippet: {snippet}\n\n"
        
        return formatted_news if formatted_news else "No new articles found."
    except Exception as e:
        print(f"Error fetching news from ChromaDB: {e}")
        return "Error: Could not fetch news from the database."

# Create the task for the Triage Agent
triage_task = Task(
    description=(
        "Here is a list of the latest financial news headlines and snippets. "
        "Your task is to analyze each one and classify it as 'Significant' if it is likely to be market-moving "
        "(e.g., major earnings reports, M&A activity, Fed announcements, significant economic data, major geopolitical events) "
        "or 'Noise' if it is general commentary, opinion, or minor news.\n\n"
        "Provide your output as a simple list. For example:\n"
        "Item 1: Significant\n"
        "Item 2: Noise\n"
        "Item 3: Significant\n"
        "\n--- LATEST NEWS ---\n"
        f"{get_latest_news_from_db()}" # Fetch and inject the news
    ),
    expected_output="A numbered list of classifications, with each line containing either 'Significant' or 'Noise'.",
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
print("Final Result:")
print(result)

