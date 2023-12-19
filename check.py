import urllib.request
import json
import time
import ssl

def ping_url(url):
    try:
        # Disable SSL/TLS certificate verification
        context = ssl._create_unverified_context()

        # Fake being Windows Firefox to avoid most bot detection
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0'}

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=context) as response:
            http_response_code = response.getcode()
            if http_response_code >= 200 or http_response_code <= 299:
                print(f"Successfully pinged {url}")
                return True
            print(f"Unsuccessfully pinged {url} - {http_response_code}")
        return False
    except urllib.error.URLError as e:
        print(f"Failed to ping {url}. Error: {e}")
        return False
    except BaseException as e:
        print(f"Failed to ping {url}. Error: {e}")
        return False


json_data = []
with open('feeds.json', 'r') as file:
    file_content = file.read()
    json_data = json.loads(file_content)

found = []
for x in json_data:
    if x in found:
        print(f"Duplicate {x}")
        continue
    found.append(x)
    if ping_url(x['url']):
        x['failCount'] = 0
    else:
        if 'failCount' not in x:
            x['failCount'] = 0
        x['failCount'] = x['failCount'] + 1
    x['lastCheckTime'] = int(time.time())


json_dump = json.dumps(json_data)

# save it out
with open('feeds2.json', 'w') as file:
    file.write(json_dump)