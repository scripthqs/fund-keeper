
with open('app/agent/tools.py', encoding='utf-8') as f:
    content = f.read()

old_start = content.find('def tool_search_web(')
old_end = content.find('\ndef execute_tool(')
if old_end == -1:
    old_end = content.find('\n\n#', old_start + 100)

print(f'Replacing lines: {old_start} to {old_end}')

new_func = '''def tool_search_web(user_id: str = "", query: str = "") -> str:
    """联网搜索 - Bing"""
    if not query:
        return "请提供搜索关键词"
    
    logger.info("联网搜索: %s", query)
    results = []
    
    try:
        resp = httpx.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "zh-cn"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            timeout=15.0,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            html = resp.text
            titles = re.findall(r'<h2[^>]*?>.*?<a[^>]*?>(.*?)</a>', html, re.DOTALL)
            paras = re.findall(r'<p[^>]*?>(.*?)</p>', html, re.DOTALL)
            clean = []
            for p in paras:
                t = re.sub(r'<[^>]+>', '', p).strip()
                t = re.sub(r'&[a-z]+;', ' ', t)
                if 40 < len(t) < 500:
                    clean.append(t)
            for i, t_html in enumerate(titles[:8]):
                title = re.sub(r'<[^>]+>', '', t_html).strip()
                if title and len(title) > 5:
                    line = f"- **{title}**"
                    if i < len(clean):
                        line += f"\\n  {clean[i][:200]}"
                    results.append(line)
    except Exception as e:
        logger.warning("Bing failed: %s", e)

    if not results:
        return f"搜索{query}暂无结果"
    return f"**搜索: {query}**\\n\\n" + "\\n\\n".join(results[:8])
'''

content = content[:old_start] + new_func + content[old_end:]
with open('app/agent/tools.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
