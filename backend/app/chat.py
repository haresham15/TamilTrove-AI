from __future__ import annotations

import logging
from typing import Any

from .schemas import SearchRequest
from .services import SearchService, ServiceContainer

logger = logging.getLogger("tamiltrove.chat")

class ChatService:
    def __init__(self, container: ServiceContainer):
        self.container = container
        self.search_service = SearchService(container)
        
        try:
            from google import genai
            # It will automatically pick up GEMINI_API_KEY from environment
            self.client = genai.Client()
            self.enabled = True
        except ImportError:
            logger.warning("google-genai not installed. Chat disabled.")
            self.client = None
            self.enabled = False
        except Exception as e:
            logger.warning(f"Error initializing genai client: {e}")
            self.client = None
            self.enabled = False

    def chat(self, request_id: str, query: str, user_id: str | None = None) -> dict[str, Any]:
        if not self.enabled or not self.client:
            return {"answer": "Chat service is not configured.", "citations": []}

        # Retrieve candidates via standard search
        search_request = SearchRequest(query=query, page_size=10)
        search_results = self.search_service.search(
            search_request, request_id=request_id, user_id=user_id
        )

        results = search_results.get("results", [])
        
        # Build context
        context_blocks = []
        for r in results:
            title = r.get("title", "")
            overview = r.get("overview", "")
            genres = ", ".join(r.get("genres", []))
            context_blocks.append(f"Title: {title}\nGenres: {genres}\nOverview: {overview}")
            
        context_str = "\n\n".join(context_blocks)
        
        prompt = f"""You are a helpful movie discovery assistant for TamilTrove. 
Use the following movie context to answer the user's question. 
If the answer is not in the context, say that you don't know based on the available catalog.

CONTEXT:
{context_str}

USER QUESTION: {query}
"""
        
        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            answer = response.text
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            answer = "Sorry, I encountered an error while generating a response."
            
        return {
            "answer": answer,
            "citations": results,
            "query": query,
        }
