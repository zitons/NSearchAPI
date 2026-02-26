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

app = FastAPI()
# 设置日志级别为 INFO
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CACHE_DIR = "/tmp/cache/"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)

def extract_text(text: str, limit=1000) -> str:
    token_pattern = re.compile(r'[A-Za-z]+|[\u4e00-\u9fff]|.', re.UNICODE)
    tokens = token_pattern.findall(text)
    return ''.join(tokens[:limit])

def get_search_results_sync(keyword: str, pages: int = 1) -> List[Dict[str, Any]]:
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.bing.com/"
    }

    for i in range(pages):
        first = 1 + i * 10
        url = f"https://www.bing.com/search?q={keyword}&first={first}"
        logging.info(f"--- [DEBUG] 正在请求第 {i+1} 页: {url} ---")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            logging.info(f"[DEBUG] HTTP 状态码: {response.status_code}")
            
            # 调试输出：检查是否被拦截
            if "Ref A:" in response.text or "Standard v3" in response.text:
                logging.warning("[DEBUG] 警告：可能触发了 Bing 的 WAF 拦截页面！")
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # 查找所有搜索条目
            items = soup.find_all("li", class_="b_algo")
            logging.info(f"[DEBUG] 本页找到 b_algo 数量: {len(items)}")
            
            if len(items) == 0:
                # 备选方案：尝试更通用的选择器（有时类名会变）
                items = soup.select(".b_algo h2 a")
                logging.info(f"[DEBUG] 备选选择器(h2 a)找到数量: {len(items)}")

            for item in items:
                # 兼容性解析逻辑
                h2 = item.find("h2")
                a_tag = h2.find("a") if h2 else item.find("a", href=True)
                
                if a_tag and a_tag.get("href"):
                    link = a_tag.get("href")
                    if link.startswith("http"):
                        results.append({
                            "title": a_tag.get_text(strip=True),
                            "link": link,
                            "description": item.get_text(strip=True)[:100]
                        })
            
        except Exception as e:
            logging.error(f"[DEBUG] 搜索请求异常: {str(e)}")
            continue

    logging.info(f"--- [DEBUG] 最终抓取到结果总数: {len(results)} ---")
    return results

async def fetch_content(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=5) as response:
            logging.info(f"[DEBUG] 爬取网站内容: {url} | Status: {response.status}")
            if response.status != 200: return f"Error {response.status}"
            soup = BeautifulSoup(await response.text(), "html.parser")
            return extract_text(soup.get_text(separator=' ', strip=True), limit=500)
    except Exception as e:
        return f"爬取失败: {str(e)}"

@app.get("/nsearch")
async def search(s: str = Query(..., description="搜索关键词"), pages: int = 1):
    logging.info(f"=== [NEW REQUEST] Query: {s} ===")
    search_results = await asyncio.to_thread(get_search_results_sync, s, pages)
    
    if not search_results:
        return JSONResponse(content={"debug_info": "未找到搜索结果，请检查 Vercel Logs", "results": []})

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_content(session, r["link"]) for r in search_results]
        crawled = await asyncio.gather(*tasks)
    
    for idx, content in enumerate(crawled):
        if idx < len(search_results):
            search_results[idx]["content"] = content
            
    return JSONResponse(content=search_results)

@app.get("/")
async def info():
    return {"status": "ok", "msg": "NSearch is active"}

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
