import httpx
resp = httpx.get(
    'https://www.bing.com/search',
    params={'q': '半导体政策'},
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
    timeout=10,
    follow_redirects=True
)
html = resp.text
print('Status:', resp.status_code, 'Len:', len(html))

# Check various patterns
for pattern in ['b_algo', 'b_results', 'b_caption', '<li class=', '<h2>', '<h2 ']:
    count = html.count(pattern)
    print(f'  "{pattern}": {count} occurrences')

# Find first search result
idx = html.find('<li class="b_')
if idx >= 0:
    chunk = html[idx:idx+500]
    print('\n--- First b_ result ---')
    print(chunk[:500])
else:
    # Try finding h2
    idx = html.find('<h2')
    if idx >= 0:
        print('\n--- First h2 ---')
        print(html[idx:idx+300])
    else:
        print('\n--- Page start ---')
        print(html[:500])
