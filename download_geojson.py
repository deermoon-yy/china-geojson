# -*- coding: UTF-8 -*-
# 获取 DataV V3 版本中国省市区县 geoJSON 地图数据
# 目录按行政区划层级归类：省文件夹 / 市文件夹 / 区县文件
# 支持：并发下载、超时重试、v3 失败自动降级到 v2、断点续传（已存在文件跳过）、错误日志

import json
import urllib.request
import urllib.error
import ssl
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

BASE_URL_V3 = "https://geo.datav.aliyun.com/areas_v3/bound/"
BASE_URL_V2 = "https://geo.datav.aliyun.com/areas_v2/bound/"

MAX_WORKERS = 5        # 并发线程数
REQUEST_INTERVAL = 0.5 # 全局最小请求间隔（秒），防止触发服务端限流
RETRY_TIMES = 5        # 每个请求最多重试次数
TIMEOUT = 15           # 请求超时时间（秒）
RETRY_INTERVAL = 2     # 重试间隔（秒）
DATA_DIR = "data"      # 数据输出目录
LOG_DIR = "log"        # 日志输出目录
DONE_LIST = os.path.join(LOG_DIR, "done.txt")  # 已完成文件清单，用于跳过已下载项

CONTEXT = ssl._create_unverified_context()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://datav.aliyun.com/",
}

# infos.json：adcode -> {name, children: [{adcode, name, ...}]}
INFOS = {}
NAME_OF = {}

_print_lock = threading.Lock()

_throttle_lock = threading.Lock()
_last_request_time = 0.0

# 进度统计：总任务数 / 已完成数
_TOTAL_TASKS = 0
_DONE_TASKS = 0
_progress_lock = threading.Lock()


def throttle():
    """全局限速：保证相邻两次请求的间隔不小于 REQUEST_INTERVAL"""
    global _last_request_time
    with _throttle_lock:
        wait = _last_request_time + REQUEST_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()


def log(msg):
    """带线程名和进度前缀的日志输出"""
    global _DONE_TASKS
    thread_name = threading.current_thread().name
    with _print_lock:
        print("[%3d/%3d] [%s] %s" % (_DONE_TASKS, _TOTAL_TASKS, thread_name, msg))


def progress_done(n=1):
    global _DONE_TASKS
    with _progress_lock:
        _DONE_TASKS += n


def get_area_code_type(code):
    """根据行政区划代码判断层级：1=省 2=市 3=区县"""
    if code[2:6] == "0000":
        return "1"
    elif code[4:6] == "00":
        return "2"
    else:
        return "3"


def log_error(e, url):
    with _print_lock:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "Error.txt"), "a+", encoding="utf-8") as f:
            f.write(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                + "\n" + str(e) + "\nin request: " + url + "\n\n"
            )


def fetch(url):
    """请求并返回 JSON 数据。url 可为字符串或候选地址列表；
    每个候选地址自动附带 v2 兜底；404 是确定性问题不重试，直接换下一个候选"""
    candidates = [url] if isinstance(url, str) else list(url)
    urls = []
    for u in candidates:
        urls.append(u)
        if u.startswith(BASE_URL_V3):
            urls.append(BASE_URL_V2 + u[len(BASE_URL_V3):])
    for i, u in enumerate(urls):
        for attempt in range(RETRY_TIMES):
            try:
                throttle()
                req = urllib.request.Request(u, headers=HEADERS)
                with urllib.request.urlopen(req, context=CONTEXT, timeout=TIMEOUT) as res:
                    return json.loads(res.read().decode("UTF-8"))
            except urllib.error.HTTPError as e:
                log_error(e, u)
                if e.code == 404:
                    log("404 Not Found，不再重试：%s" % u)
                    break  # 直接换下一个候选地址
                log("请求失败（第%d次）：%s -> %s" % (attempt + 1, u, e))
                # 403/429 大概率是限流，多等一会再重试
                time.sleep(RETRY_INTERVAL * 3 if e.code in (403, 429) else RETRY_INTERVAL)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                log("请求失败（第%d次）：%s -> %s" % (attempt + 1, u, e))
                log_error(e, u)
                if attempt < RETRY_TIMES - 1:
                    time.sleep(RETRY_INTERVAL)
        if i < len(urls) - 1:
            log("切换下一个候选地址重试")
    raise RuntimeError("最终请求失败：" + str(candidates))


_DONE_SET = set()
_done_lock = threading.Lock()


def load_done_list():
    """启动时读取已完成清单，命中项直接跳过不再发请求"""
    global _DONE_SET
    if os.path.exists(DONE_LIST):
        with open(DONE_LIST, "r", encoding="utf-8") as f:
            _DONE_SET = set(line.strip() for line in f if line.strip())
        print("从清单读取已完成记录：%d 条（%s）" % (len(_DONE_SET), DONE_LIST))


def record_done(path):
    """下载成功后追加记录到清单文件"""
    with _done_lock:
        _DONE_SET.add(path)
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(DONE_LIST, "a", encoding="utf-8") as f:
            f.write(path + "\n")


def write_json(path, data):
    """写入 JSON 文件，文件已存在则跳过（断点续传）"""
    if os.path.exists(path):
        log("文件已存在，跳过：" + path)
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    log("写入：" + path)


def load_infos():
    global INFOS, NAME_OF
    INFOS = fetch(BASE_URL_V3 + "infos.json")
    for code, val in INFOS.items():
        if "name" in val:
            NAME_OF[code] = val["name"]
        for child in val.get("children", []):
            cad = str(child["adcode"])
            NAME_OF[cad] = child["name"]


def dir_name(code):
    return "%s_%s" % (code, NAME_OF.get(code, code))


def file_name(code):
    return "%s_%s.json" % (code, NAME_OF.get(code, code))


def province_dir(code):
    return dir_name(code)


def download_one(url, path):
    """下载单个文件并写入，返回 (url, path, 错误或None)；清单命中则直接跳过"""
    if path in _DONE_SET:
        log("清单命中，跳过：" + path)
        progress_done()
        return (url, path, None)
    try:
        data = fetch(url)
        write_json(path, data)
        record_done(path)
        progress_done()
        return (url, path, None)
    except RuntimeError as e:
        progress_done()
        return (url, path, e)


_worker_seq = 0


def _init_worker():
    """给线程起简短名字，如 T1、T2"""
    global _worker_seq
    with _progress_lock:
        _worker_seq += 1
        seq = _worker_seq
    threading.current_thread().name = "T%d" % seq


def download_all(tasks):
    """并发执行下载任务，汇总失败项"""
    failures = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, initializer=_init_worker) as pool:
        futures = [pool.submit(download_one, url, path) for url, path in tasks]
        for fut in as_completed(futures):
            url, path, err = fut.result()
            if err is not None:
                log("失败：%s -> %s" % (path, err))
                failures.append(path)
    return failures


def build_tasks():
    """收集所有下载任务：(url, 输出路径)；磁盘已存在但清单未记录的先回填清单"""
    tasks = []

    def add_task(url, path):
        if path in _DONE_SET:
            return
        if os.path.exists(path):
            # 清单里没有但磁盘上有（如旧版本运行留下的文件），回填清单并跳过
            record_done(path)
            print("磁盘已存在，补记清单：" + path)
            return
        tasks.append((url, path))

    for pcode in sorted(INFOS):
        if get_area_code_type(pcode) != "1" or pcode == "100000":
            continue
        pdir = os.path.join(DATA_DIR, province_dir(pcode))
        # 省级地图（含下级边界）；部分省份（如台湾）v3 无 _full 数据，降级为自身边界
        add_task([BASE_URL_V3 + pcode + "_full.json", BASE_URL_V3 + pcode + ".json"],
                 os.path.join(pdir, file_name(pcode)))

        for child in INFOS[pcode].get("children", []):
            ccode = str(child["adcode"])
            if ccode in INFOS and INFOS[ccode].get("children"):
                # 市级：市级地图 + 区县文件
                cdir = os.path.join(pdir, dir_name(ccode))
                add_task([BASE_URL_V3 + ccode + "_full.json", BASE_URL_V3 + ccode + ".json"],
                         os.path.join(cdir, file_name(ccode)))
                for gc in INFOS[ccode].get("children", []):
                    gcode = str(gc["adcode"])
                    add_task(BASE_URL_V3 + gcode + ".json", os.path.join(cdir, file_name(gcode)))
            else:
                # 直辖市/港澳等：区划直接挂在省下
                add_task(BASE_URL_V3 + ccode + ".json", os.path.join(pdir, file_name(ccode)))

    return tasks


def main():
    print("请求行政区划信息接口...")
    load_infos()
    load_done_list()

    location_path = os.path.join(DATA_DIR, "location.json")
    if location_path not in _DONE_SET:
        write_json(location_path, INFOS)
        record_done(location_path)
    else:
        print("清单命中，跳过：" + location_path)

    # 全国地图
    china_path = os.path.join(DATA_DIR, "china.json")
    if china_path not in _DONE_SET:
        data = fetch(BASE_URL_V3 + "100000_full.json")
        write_json(china_path, data)
        record_done(china_path)
    else:
        print("清单命中，跳过：" + china_path)

    tasks = build_tasks()
    global _TOTAL_TASKS
    _TOTAL_TASKS = len(tasks)
    print("\n共 %d 个文件，%d 线程并发下载..." % (len(tasks), MAX_WORKERS))
    failures = download_all(tasks)

    if failures:
        print("\n以下 %d 个文件下载失败，可重跑脚本续传：" % len(failures))
        for p in failures:
            print("  " + p)
    else:
        print("\n全部完成")


if __name__ == "__main__":
    main()
