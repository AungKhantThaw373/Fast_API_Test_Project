import requests
from bs4 import BeautifulSoup

# Add your target URLs to this list
urls = [
    f"https://pornolab.net/forum/viewforum.php?f=1681&start={i}"
    for i in range(50, 2251, 50)
]

search_term = "451"

for url in urls:
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get all visible text on the page
        page_text = soup.get_text()
        
        if search_term in page_text:
            print(f"[FOUND] '{search_term}' exists on: {url}")
        else:
            print(f"[NOT FOUND] Checked: {url}")
    except Exception as e:
        print(f"[ERROR] Could not scan {url}: {e}")
