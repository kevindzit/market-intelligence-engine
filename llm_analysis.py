import os
import chromadb
from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import ScrapeWebsiteTool
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type
from duckduckgo_search import DDGS

# --- Configuration ---
CHROMA_PATH = "chroma_db_news"
COLLECTION_NAME = "news_articles"

# Don't set OPENAI_API_KEY at all - let it be missing

# --- Initialize ChromaDB ---
try:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)
    print(f"ChromaDB: {collection.count()} articles")
except Exception as e:
    print(f"ChromaDB error: {e}")
    exit()

# --- Initialize Models ---
try:
    # Use CrewAI's LLM wrapper instead of langchain directly
    print("Testing Ollama connection...")
    import requests
    response = requests.get("http://localhost:11434/api/tags")
    if response.status_code != 200:
        print("Ollama server: NOT responding. Run 'ollama serve'")
        exit()

    print("Ollama server: Connected")
    models = response.json().get('models', [])
    model_names = [m['name'] for m in models]
    print(f"Available models: {model_names}")

    # Use finance-optimized models for RTX 4090/5090
    # Triage: Fast 8B model for quick classification
    triage_model = "0xroyce/plutus" if "0xroyce/plutus:latest" in model_names else "llama3:8b"

    # Research: Finance-trained 8B model
    research_model = "martain7r/finance-llama-8b" if "martain7r/finance-llama-8b:latest" in model_names else "llama3:8b"

    # Master reasoning: 32B model (future - needs 4090/5090)
    reasoning_model = "qwen2.5:32b" if "qwen2.5:32b" in model_names else None

    ollama_triage = LLM(
        model=f"ollama/{triage_model}",
        base_url="http://localhost:11434"
    )
    ollama_research = LLM(
        model=f"ollama/{research_model}",
        base_url="http://localhost:11434"
    )

    print(f"Triage model: {triage_model}")
    print(f"Research model: {research_model}")
    print("Models: Ready")
except Exception as e:
    print(f"Model error: {e}")
    import traceback
    traceback.print_exc()
    exit()

# --- Custom DuckDuckGo Tool ---
class DDGSearchInput(BaseModel):
    query: str = Field(..., description="Search query")

class DuckDuckGoSearchTool(BaseTool):
    name: str = "DuckDuckGo Search"
    description: str = "Search the internet. Input: search query string."
    args_schema: Type[BaseModel] = DDGSearchInput
    
    def _run(self, query: str) -> str:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                return "No results found."
            return "\n".join([f"{i+1}. {r.get('title', '')}\n   {r.get('body', '')}\n   {r.get('href', '')}\n" 
                            for i, r in enumerate(results)])
        except Exception as e:
            return f"Search error: {e}"

# --- Tools ---
web_scraper = ScrapeWebsiteTool()
search_tool = DuckDuckGoSearchTool()

# --- Agents ---
triage_agent = Agent(
    role='Financial News Triage Specialist',
    goal='Classify news as "Investigate" or "Ignore" based on market impact.',
    backstory='Expert at identifying market-moving news quickly and accurately. Trained on 394 finance books covering stock analysis, options trading, and technical analysis.',
    verbose=False,
    allow_delegation=False,
    llm=ollama_triage
)

research_agent = Agent(
    role='Financial News Analyst',
    goal='Write brief summaries of investigated news items.',
    backstory='Financial analyst trained on 500k examples of financial QA, reasoning, and sentiment analysis. Expert at extracting actionable insights from market news.',
    verbose=False,
    allow_delegation=False,
    llm=ollama_research,
    tools=[]  # No tools - just analyze the data provided
)

# --- Fetch News ---
def get_latest_news(num=25):
    try:
        results = collection.get(include=['metadatas', 'documents'], limit=num)
        if not results or not results.get('metadatas'):
            return {'ids': [], 'metadatas': [], 'documents': []}
        
        items = []
        ids = results.get('ids', [])
        metas = results.get('metadatas', [])
        docs = results.get('documents', [])
        
        for i in range(min(len(ids), len(metas))):
            items.append((ids[i], metas[i], docs[i] if i < len(docs) else None))
        
        items.sort(key=lambda x: x[1].get('scraped_at', ''), reverse=True)
        return {'ids': [x[0] for x in items], 
                'metadatas': [x[1] for x in items], 
                'documents': [x[2] for x in items]}
    except Exception as e:
        print(f"DB fetch error: {e}")
        return {'ids': [], 'metadatas': [], 'documents': []}

latest_news = get_latest_news()

def format_news(news_data):
    if not news_data or not news_data.get('metadatas'):
        return "No articles found."
    
    formatted = ""
    for i, meta in enumerate(news_data['metadatas']):
        headline = meta.get('headline', 'No Headline')
        snippet = news_data['documents'][i] if i < len(news_data.get('documents', [])) else 'No Snippet'
        url = meta.get('url', 'No URL')
        formatted += f"Item {i+1}:\nURL: {url}\nHeadline: {headline}\nSnippet: {snippet}\n\n"
    return formatted

news_content = format_news(latest_news) if latest_news else "Error fetching news."

# --- Tasks ---
triage_task = Task(
    description=(
        "Analyze each news item and output ONLY 'Investigate' or 'Ignore' for each.\n\n"
        "RULES:\n"
        "- 'Investigate': Major earnings, M&A, Fed news, CEO changes, economic data, geopolitics\n"
        "- 'Ignore': Commentary, opinions, minor news, advice\n\n"
        "OUTPUT FORMAT - FOLLOW EXACTLY:\n"
        "1. Investigate\n"
        "2. Ignore\n"
        "3. Investigate\n"
        "(and so on for all items)\n\n"
        "NEWS ITEMS:\n"
        f"{news_content}"
    ),
    expected_output="A numbered list with ONLY the word 'Investigate' or 'Ignore' on each line. No explanations.",
    agent=triage_agent,
    output_file="outputs/triage_results.txt"
)

research_task = Task(
    description=(
        "Write brief summaries for the first 5 items marked 'Investigate'.\n\n"
        "News items:\n"
        f"{news_content}\n\n"
        "For each investigated item, write 2-3 sentences explaining:\n"
        "- What happened\n"
        "- Why it matters for markets\n\n"
        "Format:\n"
        "Item X: [Headline]\n"
        "[Your 2-3 sentence summary]\n\n"
    ),
    expected_output="Brief summaries for first 5 investigated items based on headlines and snippets.",
    agent=research_agent,
    context=[triage_task]
)

# --- Run Crew ---
crew = Crew(
    agents=[triage_agent, research_agent],
    tasks=[triage_task, research_task],
    process=Process.sequential,
    verbose=False,
    memory=False  # CRITICAL: Disable memory to avoid OpenAI embedding errors
)

print("\nRunning analysis...")
try:
    result = crew.kickoff()
    
    # Show triage results for debugging
    print("\n=== TRIAGE RESULTS ===")
    try:
        with open("outputs/triage_results.txt", 'r') as f:
            triage_content = f.read()
            print(triage_content)  # Show full content

            # Count investigations
            investigate_count = triage_content.lower().count('investigate')
            ignore_count = triage_content.lower().count('ignore')
            print(f"\nStats: {investigate_count} Investigate, {ignore_count} Ignore")
    except Exception as e:
        print(f"Could not read outputs/triage_results.txt: {e}")
    
    print("\n=== RESEARCH RESULTS ===")
    if result:
        print(result)
    else:
        print("No results produced.")
        
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()

print("\n=== DONE ===")