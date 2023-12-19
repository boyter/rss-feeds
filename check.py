import urllib.request
import json
import time

def ping_url(url):
    try:
        urllib.request.urlopen(url)
        print(f"Successfully pinged {url}")
        return True
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

for x in json_data:

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
    file.write()