from langchain.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()

tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


@tool
def web_search(query: str) -> str:
    """
    Search the web for recent and reliable information.
    Returns titles, URLs, and snippets.
    """

    results = tavily.search(
        query=query,
        max_results=5
    )

    output = []

    for r in results.get("results", []):
        output.append(
            f"Title: {r.get('title','N/A')}\n"
            f"URL: {r.get('url','N/A')}\n"
            f"Snippet: {r.get('content','')[:300]}"
        )

    return "\n-----\n".join(output)


@tool
def scrape_url(url: str) -> str:
    """
    Scrape a webpage and return its text content.
    """

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup(
            ["script", "style", "nav", "footer", "header"]
        ):
            tag.decompose()

        text = soup.get_text(
            separator=" ",
            strip=True
        )

        return text[:10000]

    except requests.RequestException as e:
        return f"Error scraping URL: {e}"