import urllib.request
import json
import time
import ssl
import threading
import concurrent.futures

results = []
lock = threading.Lock()

def record(url, success):
    with lock:
        if not success:
            if 'failCount' not in url:
                url['failCount'] = 0
            url['failCount'] = url['failCount'] + 1

        url['lastCheckTime'] = int(time.time())
        results.append(url)

def ping_url(url):
    try:
        # Disable SSL/TLS certificate verification
        context = ssl._create_unverified_context()

        # Fake being Windows Firefox to avoid most bot detection
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0'}

        req = urllib.request.Request(url['url'], headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=context) as response:
            http_response_code = response.getcode()
            if http_response_code >= 200 or http_response_code <= 299:
                print(f"Successfully pinged {url['url']}")
                record(url, True)
                return True
            print(f"Unsuccessfully pinged {url['url']} - {http_response_code}")
        record(url, False)
        return False
    except urllib.error.URLError as e:
        print(f"Failed to ping {url['url']}. Error: {e}")
        record(url, False)
        return False
    except BaseException as e:
        print(f"Failed to ping {url['url']}. Error: {e}")
        record(url, False)
        return False


# Load the feeds so we can start checking them
json_data = []
with open('feeds.json', 'r') as file:
    file_content = file.read()
    json_data = json.loads(file_content)
    
# Spawn 50 threads so we can process this quickly
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    futures = {executor.submit(ping_url, url): url for url in json_data}

    # Wait for all tasks to complete
    concurrent.futures.wait(futures)

# Dump it and save it
json_dump = json.dumps(results)
with open('feeds.json', 'w') as file:
    file.write(json_dump)
