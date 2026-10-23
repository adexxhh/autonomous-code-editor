import pytest
import worker

@pytest.fixture(autouse=True)
def offline_search(monkeypatch):
    class Search:
        def text(self, query, max_results=3):
            return [{"title": "fixture", "body": query}]
    monkeypatch.setattr(worker, "DDGS", Search)
