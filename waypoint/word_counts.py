"""Deterministic English word counts, never a model invocation."""
import re
TOKENS=re.compile(r'https?://[^\s]+|[A-Za-z0-9]+(?:[.,][0-9]+)*(?:[\u2019\x27-][A-Za-z0-9]+)*')
def count_words(text):return len(TOKENS.findall(str(text or '')))
def word_counts(title,body):
    a=count_words(title);b=count_words(body)
    return {'title':a,'body':b,'total':a+b}
def counted(revision):
    return revision|{'word_counts':word_counts(revision.get('title'),revision.get('body'))} if revision.get('stage')=='english' else revision
