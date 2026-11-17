"""
A complete Django application in one file: a middleware, two views and
the helpers they use, driven by Django's test client.

    $ pip install django
    $ pyftrace examples/django_example.py

A request passes through dozens of Django functions before it reaches a
view.  pyftrace leaves library code out by default, so the trace shows
only the code in this file: which middleware, view and helper run for
each request, in which order, and where the 404 of the last request is
raised.

    $ pyftrace -a examples/django_example.py      # with arguments
    $ pyftrace -f article_detail examples/django_example.py
    $ pyftrace -v -d 6 examples/django_example.py # into Django itself
"""
import time

import django
from django.conf import settings
from django.http import Http404, JsonResponse
from django.test import Client
from django.urls import path

ARTICLES = {
    1: {"title": "Tracing Python", "body": "Use sys.monitoring."},
    2: {"title": "Tracing Django", "body": "Start with the views."},
}

def find_article(article_id):
    if article_id not in ARTICLES:
        raise Http404(f"No article {article_id}")
    return ARTICLES[article_id]

def serialize(article_id, article, with_body=False):
    data = {"id": article_id, "title": article["title"]}
    if with_body:
        data["body"] = article["body"]
    return data

def article_list(request):
    articles = []
    for article_id, article in ARTICLES.items():
        articles.append(serialize(article_id, article))
    return JsonResponse({"articles": articles})

def article_detail(request, article_id):
    article = find_article(article_id)
    return JsonResponse(serialize(article_id, article, with_body=True))

class TimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)
        response["X-Elapsed"] = f"{time.perf_counter() - started:.6f}"
        return response

urlpatterns = [
    path("articles/", article_list),
    path("articles/<int:article_id>/", article_detail),
]

def main():
    settings.configure(
        SECRET_KEY="not a secret, this is an example",
        ROOT_URLCONF=__name__,
        MIDDLEWARE=[f"{__name__}.TimingMiddleware"],
        ALLOWED_HOSTS=["testserver"],
        LOGGING_CONFIG=None,
    )
    django.setup()

    client = Client()
    for url in ("/articles/", "/articles/1/", "/articles/99/"):
        response = client.get(url)
        print(f"GET {url} -> {response.status_code}")

if __name__ == "__main__":
    main()
