import os
import json
import asyncio
import aiohttp
import logging
import re
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from bs4 import BeautifulSoup
from typing import List, Dict, Any

# --- [ 核心修改 1: 环境适配 ] ---
app = FastAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Vercel 只有 /tmp 是可写的，且不需要 initialize_cache 的复杂逻辑
CACHE_DIR = "/tmp/cache/"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)

# --- [ 核心功能函数 ] ---
def extract_text(text: str, limit=1000) -> str:
    sentence_endings = {'.', ';', '?', '。', '；', '？'}
    extracted = []
    count = 0
    stop = False
    token_pattern = re.compile(r'[A-Za-z]+|[\u4e00-\u9fff]|.', re.UNICODE)
    tokens = token_pattern.findall(text)
    for token in tokens:
        count += 1
        extracted.append(token)
        if count >= limit and not stop: stop = True
        if stop and token in sentence_endings: break
        if count > limit + 100: break
    return ''.join(extracted)

def get_search_results_sync(keyword: str, pages: int = 1) -> List[Dict[str, Any]]:
    results = []
    # Vercel 的缓存是临时的，仅在单次容器生命周期有效
    cache_filename = os.path.join(CACHE_DIR, f"search_{hash(keyword)}_{pages}.json")

    if os.path.exists(cache_filename):
        try:
            with open(cache_filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.95 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.bing.com/"
    }

    for i in range(pages):
        first = 1 + i * 10
        url = f"https://cn.bing.com/search?q={keyword}&first={first}"
        try:
            response = requests.get(url, headers=headers, timeout=8)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            for result in soup.find_all("li", class_="b_algo"):
                h2 = result.find("h2")
                a_tag = h2.find("a") if h2 else result.find("a", href=True)
                if a_tag and a_tag.get("href"):
                    link = a_tag.get("href").strip()
                    # 自动清理加密链接（如果需要更高级解密，明天我们再加）
                    if "/ck/ms?" in link: continue 
                    results.append({
                        "title": a_tag.get_text(strip=True),
                        "link": link,
                        "description": result.get_text(strip=True)[:200]
                    })
        except Exception as e:
            logging.error(f"Bing 搜索失败: {e}")
            continue

    with open(cache_filename, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    return results

async def fetch_content(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=5) as response:
            if response.status != 200: return f"Error {response.status}"
            soup = BeautifulSoup(await response.text(), "html.parser")
            return extract_text(soup.get_text(separator=' ', strip=True), limit=800)
    except: return "爬取失败"

# --- [ 路由接口 ] ---
@app.get("/nsearch")
async def search(s: str = Query(..., description="搜索关键词"), pages: int = 1):
    search_results = await asyncio.to_thread(get_search_results_sync, s, pages)
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_content(session, r["link"]) for r in search_results if r["link"].startswith("http")]
        crawled = await asyncio.gather(*tasks)
    
    for idx, content in enumerate(crawled):
        if idx < len(search_results): search_results[idx]["content"] = content
    return JSONResponse(content=search_results)

@app.get("/")
async def info():
    return {"title": "NSearch API on Vercel", "status": "running"}

# --- [ 核心修改 2: 删掉所有命令行 UI 和 main 函数 ] ---
# 无需 if __name__ == "__main__": 逻辑
