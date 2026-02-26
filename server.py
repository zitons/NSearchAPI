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

# 配置日志：确保在 Vercel 控制台能看到实时输出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Vercel 环境下只有 /tmp 是可写的
CACHE_DIR = "/tmp/cache/"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)

def extract_text(text: str, limit=1000) -> str:
    """提取纯文本并限制长度"""
    token_pattern = re.compile(r'[A-Za-z]+|[\u4e00-\u9fff]|.', re.UNICODE)
    tokens = token_pattern.findall(text)
    return ''.join(tokens[:limit])

def get_search_results_sync(keyword: str, pages: int = 1) -> List[Dict[str, Any]]:
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.bing.com/"
    }

    for i in range(pages):
        first = i * 10 + 1
        url = f"https://www.bing.com/search?q={keyword}&first={first}"
        logging.info(f"[DEBUG] 正在尝试请求: {url}")
        
        try:
            with requests.Session() as s:
                response = s.get(url, headers=headers, timeout=10)
                logging.info(f"[DEBUG] HTTP 状态码: {response.status_code}")
                
                # 检查是否被拦截 (Ref A 是 Bing 拦截的典型特征)
                if "Ref A:" in response.text or "验证" in response.text:
                    logging.error("[!] 触发拦截页面，跳过此页")
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                
                # 方案 A: 寻找标准结果块
                items = soup.find_all("li", class_="b_algo")
                logging.info(f"[DEBUG] 方案 A 找到条目: {len(items)}")
                
                # 方案 B: 备选通用选择器（修正了之前的缩进问题）
                if not items:
                    logging.info("[DEBUG] 方案 A 失败，尝试方案 B (CSS Selector)")
                    items = soup.select("#b_results .b_algo, #b_results h2 a")
                    logging.info(f"[DEBUG] 方案 B 找到条目: {len(items)}")

                for item in items:
                    try:
                        if item.name == 'a':
                            a_tag = item
                            parent = item.find_parent("li") or item
                        else:
                            a_tag = item.find("a", href=True)
                            parent = item
                        
                        if not a_tag: continue
                        
                        link = a_tag.get("href", "")
                        if link.startswith("http") and "bing.com" not in link:
                            results.append({
                                "title": a_tag.get_text(strip=True),
                                "link": link,
                                "description": parent.get_text(strip=True)[:150]
                            })
                    except Exception:
                        continue
        except Exception as e:
            logging.error(f"[ERROR] 抓取崩溃: {str(e)}")
            
    # 去重逻辑
    seen = set()
    unique_results = []
    for res in results:
        if res['link'] not in seen:
            seen.add(res['link'])
            unique_results.append(res)
            
    return unique_results

async def fetch_content(session: aiohttp.ClientSession, url: str) -> str:
    """异步抓取目标网页内容"""
    try:
        async with session.get(url, timeout=5) as response:
            if response.status != 200: return f"HTTP {response.status}"
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            # 移除干扰元素
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text(separator=' ', strip=True)
            return extract_text(text, limit=600)
    except Exception as e:
        return f"爬取失败: {str(e)}"

@app.get("/nsearch")
async def nsearch(s: str = Query(..., description="搜索关键词"), pages: int = 1):
    logging.info(f"=== [收到新请求] 关键词: {s} ===")
    
    # 获取搜索列表 (在线程池中运行同步请求)
    search_results = await asyncio.to_thread(get_search_results_sync, s, pages)
    
    if not search_results:
        return JSONResponse(content={"status": "empty", "results": []})

    # 并发爬取内容
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = [fetch_content(session, r["link"]) for r in search_results]
        contents = await asyncio.gather(*tasks)
    
    for idx, content in enumerate(contents):
        if idx < len(search_results):
            search_results[idx]["content"] = content
            
    return JSONResponse(content=search_results)

@app.get("/")
async def root():
    return {"status": "ok", "service": "NSearch-Vercel"}
    for i in range(pages):
        first = i * 10 + 1
        url = f"https://www.bing.com/search?q={keyword}&first={first}"
        logging.info(f"[DEBUG] Requesting: {url}")
        
        try:
            with requests.Session() as s:
                response = s.get(url, headers=headers, timeout=10)
                logging.info(f"[DEBUG] Status: {response.status_code}")
                
                # 检查是否被拦截
                if "Ref A:" in response.text or "验证" in response.text:
                    logging.error("[!] Blocked by Bing")
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                
                # 方案 A
                items = soup.find_all("li", class_="b_algo")
                logging.info(f"[DEBUG] Scheme A found: {len(items)}")
                
                # 方案 B
                if not items:
                    logging.info("[DEBUG] Switching to Scheme B")
                    items = soup.select("#b_results .b_algo, #b_results h2 a")
                    logging.info(f"[DEBUG] Scheme B found: {len(items)}")

                for item in items:
                    try:
                        if item.name == 'a':
                            a_tag = item
                            parent = item.find_parent("li") or item
                        else:
                            a_tag = item.find("a", href=True)
                            parent = item
                        
                        if not a_tag: continue
                        
                        link = a_tag.get("href", "")
                        if link.startswith("http") and "bing.com" not in link:
                            results.append({
                                "title": a_tag.get_text(strip=True),
                                "link": link,
                                "description": parent.get_text(strip=True)[:150]
                            })
                    except:
                        continue
        except Exception as e:
            logging.error(f"[ERROR] {str(e)}")
            
    seen = set()
    unique_results = []
    for res in results:
        if res['link'] not in seen:
            seen.add(res['link'])
            unique_results.append(res)
    return unique_results

async def fetch_content(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=5) as response:
            if response.status != 200: return f"HTTP {response.status}"
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text(separator=' ', strip=True)
            return extract_text(text, limit=600)
    except Exception as e:
        return f"Fail: {str(e)}"

@app.get("/nsearch")
async def nsearch(s: str = Query(..., description="Query"), pages: int = 1):
    logging.info(f"=== Request Query: {s} ===")
    search_results = await asyncio.to_thread(get_search_results_sync, s, pages)
    
    if not search_results:
        return JSONResponse(content={"status": "empty", "results": []})

    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = [fetch_content(session, r["link"]) for r in search_results]
        contents = await asyncio.gather(*tasks)
    
    for idx, content in enumerate(contents):
        if idx < len(search_results):
            search_results[idx]["content"] = content
            
    return JSONResponse(content=search_results)

@app.get("/")
async def root():
    return {"status": "ok", "service": "NSearch"}
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1"
    }

    for i in range(pages):
        first = i * 10 + 1
        url = f"https://www.bing.com/search?q={keyword}&first={first}"
        logging.info(f"[DEBUG] 正在尝试请求 URL: {url}")
        
        try:
            # 使用 Session 模拟真实访问
            with requests.Session() as s:
                response = s.get(url, headers=headers, timeout=10)
                logging.info(f"[DEBUG] HTTP 响应码: {response.status_code}")
                
                # 打印前 1000 字符用于排查是否被拦截
                snippet = response.text[:1000].replace('\n', ' ')
                logging.info(f"[DEBUG] 页面源码片段: {snippet}")

                if "Ref A:" in response.text or "验证" in response.text:
                    logging.error("[!] 探测到拦截页面或验证码，IP 可能已被风控")
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                
                # 方案 A: 寻找标准结果块
                items = soup.find_all("li", class_="b_algo")
                logging.info(f"[DEBUG] 方案 A (b_algo) 找到条目: {len(items)}")
                
                # 方案 B: 备选通用选择器
                if not items:
                    logging.info("[DEBUG] 方案 A 失败，尝试方案 B (CSS Selector)")
                    items = soup.select("#b_results .b_algo, #b_results h2 a")
                    logging.info(f"[DEBUG] 方案 B 找到条目: {len(items)}")

                for item in items:
                    try:
                        # 容错解析：可能是 a 标签也可能是包含 a 的块
                        if item.name == 'a':
                            a_tag = item
                            parent = item.find_parent("li") or item
                        else:
                            a_tag = item.find("a", href=True)
                            parent = item
                        
                        if not a_tag: continue
                        
                        link = a_tag.get("href", "")
                        # 过滤掉广告链接和 Bing 内部链接
                        if link.startswith("http") and "bing.com" not in link:
                            results.append({
                                "title": a_tag.get_text(strip=True),
                                "link": link,
                                "description": parent.get_text(strip=True)[:150]
                            })
                    except Exception as e:
                        logging.debug(f"单条结果解析失败: {e}")
                        continue

        except Exception as e:
            logging.error(f"[ERROR] 搜索请求发生崩溃: {str(e)}")
            
    # 去重
    seen_links = set()
    unique_results = []
    for res in results:
        if res['link'] not in seen_links:
            seen_links.add(res['link'])
            unique_results.append(res)
            
    return unique_results

async def fetch_content(session: aiohttp.ClientSession, url: str) -> str:
    """异步抓取目标网页内容"""
    try:
        async with session.get(url, timeout=5) as response:
            if response.status != 200:
                return f"HTTP {response.status}"
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text(separator=' ', strip=True)
            return extract_text(text, limit=600)
    except Exception as e:
        return f"爬取失败: {str(e)}"

@app.get("/nsearch")
async def nsearch(s: str = Query(..., description="搜索关键词"), pages: int = 1):
    logging.info(f"=== [收到新请求] 关键词: {s} ===")
    
    # 1. 获取搜索列表
    search_results = await asyncio.to_thread(get_search_results_sync, s, pages)
    
    if not search_results:
        return JSONResponse(content={
            "status": "empty",
            "message": "未找到结果，请查看 Vercel Logs 中的源码片段排查拦截情况",
            "results": []
        })

    # 2. 异步爬取具体内容
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = [fetch_content(session, r["link"]) for r in search_results]
        contents = await asyncio.gather(*tasks)
    
    for idx, content in enumerate(contents):
        if idx < len(search_results):
            search_results[idx]["content"] = content
            
    return JSONResponse(content=search_results)

@app.get("/")
async def root():
    return {"status": "ok", "service": "NSearch-Vercel"}
                # 方案 B: 如果 A 失败，寻找所有带链接的 H2
                if not items:
                    logging.info("[DEBUG] 方案 A 失败，启动方案 B (CSS Selector)")
                    # 匹配任何在搜索结果区域的标题链接
                    items = soup.select("#b_results .b_algo, #b_results h2 a")

                for item in items:
                    # 这里的解析逻辑要更具容错性
                    try:
                        if item.name == 'a':
                            a_tag = item
                            parent = item.find_parent("li") or item
                        else:
                            a_tag = item.find("a", href=True)
                            parent = item
                        
                        link = a_tag.get("href", "")
                        if link.startswith("http") and "bing.com" not in link:
                            results.append({
                                "title": a_tag.get_text(strip=True),
                                "link": link,
                                "description": parent.get_text(strip=True)[:100]
                            })
                    except:
                        continue

        except Exception as e:
            logging.error(f"[ERROR] 请求失败: {str(e)}")
            
    # 去重处理
    unique_results = {res['link']: res for res in results}.values()
    return list(unique_results)

# ... (剩下的 /nsearch 路由逻辑保持不变)
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
