import os
import asyncio
import aiohttp
import logging
import re
import requests
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from bs4 import BeautifulSoup

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Vercel 唯一可写的临时目录
CACHE_DIR = "/tmp/cache/"
os.makedirs(CACHE_DIR, exist_ok=True)

def extract_text(text: str, limit: int = 1000) -> str:
    tokens = re.findall(r'[A-Za-z]+|[\u4e00-\u9fff]|.', text)
    return ''.join(tokens[:limit])

def get_search_results_sync(keyword: str, pages: int = 1) -> list:
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.bing.com/"
    }
    
    for i in range(pages):
        first = i * 10 + 1
        url = f"https://www.bing.com/search?q={keyword}&first={first}"
        try:
            with requests.Session() as s:
                s.cookies.set("SRCHHPGUSR", "ULSR=1", domain=".bing.com")
                res = s.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")
                
                # 方案 A: 经典 b_algo
                items = soup.find_all("li", class_="b_algo")
                if not items:
                    # 方案 B: 备用选择器
                    items = soup.select("#b_results .b_algo, #b_results h2 a")
                    
                for item in items:
                    a_tag = item if item.name == 'a' else item.find("a", href=True)
                    if not a_tag:
                        continue
                    link = a_tag.get("href", "")
                    if link.startswith("http") and "bing.com" not in link:
                        results.append({
                            "title": a_tag.get_text(strip=True),
                            "link": link,
                            "description": item.get_text(strip=True)[:150]
                        })
        except Exception as e:
            logging.error(f"Error fetching page {i}: {e}")
            
    # 简易去重
    seen = set()
    unique_results = []
    for r in results:
        if r['link'] not in seen:
            seen.add(r['link'])
            unique_results.append(r)
            
    return unique_results

async def fetch_content(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                # 剔除 JS 和 CSS 干扰
                for script in soup(["script", "style"]):
                    script.decompose()
                return extract_text(soup.get_text(separator=' ', strip=True), 600)
            return f"HTTP {response.status}"
    except Exception as e:
        return f"Fetch Error: {str(e)}"

@app.get("/nsearch")
async def nsearch(s: str = Query(...), pages: int = 1):
    search_results = await asyncio.to_thread(get_search_results_sync, s, pages)
    
    # 【透视侦察模式】如果抓取为空，直接返回原网页代码供你排查
    if not search_results:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.bing.com/"
        }
        url = f"https://www.bing.com/search?q={s}&first=1"
        try:
            with requests.Session() as session:
                session.cookies.set("SRCHHPGUSR", "ULSR=1", domain=".bing.com")
                res = session.get(url, headers=headers, timeout=10)
                raw_html = res.text[:2000] # 截取前两千字
        except Exception as e:
            raw_html = f"请求失败: {str(e)}"
            
        return JSONResponse(content={
            "status": "empty",
            "reason": "未匹配到搜索结果，请检查 debug_html_snippet 是否有被拦截的提示。",
            "debug_html_snippet": raw_html,
            "results": []
        })
        
    # 如果抓取成功，并发爬取具体网站内容
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = [fetch_content(session, r["link"]) for r in search_results]
        contents = await asyncio.gather(*tasks)
        
    for idx, content in enumerate(contents):
        if idx < len(search_results):
            search_results[idx]["content"] = content
            
    return JSONResponse(content=search_results)

@app.get("/")
async def root():
    return {"status": "ok", "msg": "NSearch API is running"}
                s.cookies.set("SRCHHPGUSR", "ULSR=1", domain=".bing.com")
                res = s.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")
                
                items = soup.find_all("li", class_="b_algo")
                if not items:
                    items = soup.select("#b_results .b_algo, #b_results h2 a")
                    
                for item in items:
                    a_tag = item if item.name == 'a' else item.find("a", href=True)
                    if not a_tag:
                        continue
                    link = a_tag.get("href", "")
                    if link.startswith("http") and "bing.com" not in link:
                        results.append({
                            "title": a_tag.get_text(strip=True),
                            "link": link,
                            "description": item.get_text(strip=True)[:150]
                        })
        except Exception as e:
            logging.error(f"Error fetching page {i}: {e}")
            
    return results

async def fetch_content(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                return extract_text(soup.get_text(separator=' ', strip=True), 600)
            return f"HTTP {response.status}"
    except Exception as e:
        return f"Fetch Error: {str(e)}"

@app.get("/nsearch")
async def nsearch(s: str = Query(...), pages: int = 1):
    search_results = await asyncio.to_thread(get_search_results_sync, s, pages)
    
    if not search_results:
        return JSONResponse(content={"status": "empty", "results": []})
        
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_content(session, r["link"]) for r in search_results]
        contents = await asyncio.gather(*tasks)
        
    for idx, content in enumerate(contents):
        if idx < len(search_results):
            search_results[idx]["content"] = content
            
    return JSONResponse(content=search_results)

@app.get("/")
async def root():
    return {"status": "ok", "msg": "NSearch API is running"}
