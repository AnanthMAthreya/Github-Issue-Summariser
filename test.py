from urllib.parse import urlparse
parsed=urlparse("https://github.com/AnanthMAthreya/Github-Issue-Summariser.git")
parts = [p for p in parsed.path.split("/") if p]
print(parts)
