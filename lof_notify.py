"""
LOF基金溢价率监控 + 微信推送（Server酱）
用于 GitHub Actions 定时运行
"""

import requests
import re
import time
import os
import csv
from datetime import datetime

# ─── 基金列表 ────────────────────────────────────────────────────────────────
FUNDS = [
    ("SH501300", "501300", "美元债LOF"),
    ("SZ160140", "160140", "美国REIT精选LOF"),
    ("SZ161126", "161126", "标普医疗保健LOF"),
    ("SZ161128", "161128", "标普信息科技LOF"),
    ("SZ162415", "162415", "美国消费LOF"),
    ("SZ164824", "164824", "印度基金LOF"),
    ("SZ164906", "164906", "中概互联网LOF"),
    ("SZ161127", "161127", "标普生物科技LOF"),
    ("SZ162411", "162411", "华宝油气LOF"),
    ("SZ160416", "160416", "石油基金LOF"),
    ("SZ162719", "162719", "石油LOF"),
    ("SZ163208", "163208", "全球油气能源LOF"),
    ("SZ161815", "161815", "抗通胀LOF"),
    ("SZ161130", "161130", "纳斯达克100LOF"),
    ("SZ161125", "161125", "标普500LOF"),
    ("SH501225", "501225", "全球芯片LOF"),
    ("SH501312", "501312", "海外科技LOF"),
    ("SZ160644", "160644", "港美互联网LOF"),
    ("SZ160216", "160216", "国泰商品LOF"),
    ("SZ160719", "160719", "嘉实黄金LOF"),
    ("SZ161116", "161116", "黄金主题LOF"),
    ("SZ164701", "164701", "黄金LOF"),
    ("SZ165513", "165513", "中信保诚商品LOF"),
    ("SH501018", "501018", "南方原油LOF"),
    ("SZ160723", "160723", "嘉实原油LOF"),
    ("SZ161129", "161129", "原油LOF易方达"),
    ("SH501025", "501025", "香港银行LOF"),
    ("SZ161124", "161124", "港股小盘LOF"),
    ("SZ160717", "160717", "H股LOF"),
    ("SZ161831", "161831", "恒生国企LOF"),
    ("SH501302", "501302", "恒生指数基金LOF"),
    ("SZ160924", "160924", "恒生指数LOF"),
    ("SZ164705", "164705", "恒生LOF"),
    ("SH501043", "501043", "沪深300LOF"),
    ("SZ161226", "161226", "国投白银LOF"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Referer": "https://fund.eastmoney.com/",
}

# ─── 数据获取（复用 lof_tracker.py 的逻辑）────────────────────────────────────

def fetch_premium_single(full_code):
    ex = "sh" if full_code.startswith("SH") else "sz"
    code6 = full_code[2:]
    url = f"https://palmmicro.com/woody/res/{ex}{code6}cn.php"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.encoding = "utf-8"
        html = r.text
        m = re.search(
            r'<font[^>]*>([\d.]+)</font></td><td[^>]*>[\d-]+</td><td[^>]*><font[^>]*>([-\d.]+)%</font>',
            html
        )
        if m:
            return {"est": float(m.group(1)), "premium": float(m.group(2))}
    except Exception as e:
        print(f"  {full_code} 溢价获取失败: {e}")
    return {}

def fetch_premium():
    print("获取溢价率...")
    result = {}
    for full_code, _, _ in FUNDS:
        data = fetch_premium_single(full_code)
        if data:
            result[full_code] = data
        time.sleep(0.3)
    print(f"  完成：{len(result)} 只")
    return result

def fetch_prices():
    print("获取实时行情...")
    codes = ",".join(
        ("sh" if f[0].startswith("SH") else "sz") + f[1] for f in FUNDS
    )
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={codes}",
            headers={**HEADERS, "Referer": "https://finance.sina.com.cn"},
            timeout=15
        )
        r.encoding = "gbk"
        result = {}
        for line in r.text.splitlines():
            m = re.match(r'var hq_str_(s[hz])(\d{6})="([^"]+)"', line)
            if not m:
                continue
            full_code = m.group(1).upper() + m.group(2)
            parts = m.group(3).split(",")
            if len(parts) < 4:
                continue
            try:
                price = float(parts[3])
                prev = float(parts[2]) if parts[2] else 0
                change = round((price - prev) / prev * 100, 2) if prev else 0
                result[full_code] = {"price": price, "change": change}
            except:
                pass
        print(f"  完成：{len(result)} 只")
        return result
    except Exception as e:
        print(f"  行情获取失败: {e}")
        return {}

def parse_money_str(s):
    s = s.replace(",", "").strip()
    m = re.match(r'([\d.]+)\s*万元?', s)
    if m: return float(m.group(1)) * 10000
    m = re.match(r'([\d.]+)\s*亿元?', s)
    if m: return float(m.group(1)) * 1e8
    m = re.match(r'([\d.]+)\s*元?', s)
    if m: return float(m.group(1))
    return None

def fetch_quota_batch(codes6_batch):
    fcodes = ",".join(codes6_batch)
    url = (
        f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNFInfo"
        f"?pageIndex=1&pageSize={len(codes6_batch)}&plat=Android"
        f"&appType=ttjj&product=EFund&Version=1&Fcodes={fcodes}"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        if not data.get("Datas"):
            return {}
        result = {}
        for item in data["Datas"]:
            code = item.get("FCODE", "")
            sgzt = str(item.get("SGZT", "0"))
            sgsxe = float(item.get("SGSXE") or 0)
            sgba = float(item.get("SGBA") or 0)
            if sgzt == "1":
                status, status_text = "closed", "暂停申购"
            elif sgzt == "3":
                status, status_text = "closed", "封闭期"
            elif sgzt == "2":
                status, status_text = "limited", "限制大额"
            elif sgsxe > 0:
                status, status_text = "limited", "限额申购"
            else:
                status, status_text = "open", "正常申购"
            result[code] = {
                "status": status, "status_text": status_text,
                "quota": sgsxe if sgsxe > 0 else None,
                "big_quota": sgba if sgba > 0 else None,
            }
        return result
    except:
        return {}

def fetch_quota_page(code6):
    try:
        r = requests.get(f"https://fund.eastmoney.com/{code6}.html", headers=HEADERS, timeout=10)
        r.encoding = "utf-8"
        html = r.text
        raw_cells = re.findall(r'class="staticCell"[^>]*>(.*?)</span>\s*(?=<span|<div|$)', html, re.S)
        cells = [re.sub(r'<[^>]+>', '', c) for c in raw_cells]
        cell_text = " ".join(c.strip() for c in cells)
        status, status_text, quota = "unknown", "未知", None
        if "暂停申购" in cell_text or "暂停大额" in cell_text:
            status, status_text = "closed", "暂停申购"
        elif "封闭期" in cell_text:
            status, status_text = "closed", "封闭期"
        elif "限大额" in cell_text or "限制大额" in cell_text:
            status, status_text = "limited", "限制大额"
        elif "开放申购" in cell_text or "正常申购" in cell_text:
            status, status_text = "open", "正常申购"
        for target in [cell_text, html]:
            for pat in [r'单日累计购买上限\s*([\d.,]+\s*[万亿]?元?)',
                        r'单笔限购[：:]\s*([\d.,]+\s*[万亿]?元?)',
                        r'每日累计限购[：:]\s*([\d.,]+\s*[万亿]?元?)']:
                m = re.search(pat, target)
                if m:
                    quota = parse_money_str(m.group(1))
                    break
            if quota:
                break
        if quota and status not in ("closed",):
            status = "limited"
            status_text = "限制大额" if "限大额" in cell_text else "限额申购"
        return {"status": status, "status_text": status_text, "quota": quota, "big_quota": None}
    except Exception as e:
        print(f"  网页抓取失败 {code6}: {e}")
        return {"status": "error", "status_text": "查询失败", "quota": None, "big_quota": None}

def fetch_quota():
    print("获取限购状态...")
    all_codes = [f[1] for f in FUNDS]
    result = {}
    for i in range(0, len(all_codes), 20):
        result.update(fetch_quota_batch(all_codes[i:i+20]))
        time.sleep(0.5)
    failed = [f[1] for f in FUNDS if f[1] not in result]
    if failed:
        print(f"  App API 未返回 {len(failed)} 只，改用网页...")
        for code6 in failed:
            result[code6] = fetch_quota_page(code6)
            time.sleep(0.3)
    print(f"  完成")
    return result

def merge(premium_map, price_map, quota_map):
    rows = []
    for full_code, code6, name in FUNDS:
        p = price_map.get(full_code, {})
        e = premium_map.get(full_code, {})
        q = quota_map.get(code6, {"status": "error", "status_text": "查询失败", "quota": None, "big_quota": None})
        price = p.get("price")
        change = p.get("change")
        est = e.get("est")
        premium = e.get("premium")
        if premium is None and price and est:
            premium = round((price - est) / est * 100, 2)
        rows.append({
            "full_code": full_code, "code6": code6, "name": name,
            "price": price, "change": change, "est": est, "premium": premium,
            "status": q["status"], "status_text": q["status_text"],
            "quota": q["quota"], "big_quota": q["big_quota"],
        })
    rows.sort(key=lambda x: (x["premium"] or -999), reverse=True)
    return rows

# ─── 格式化 ──────────────────────────────────────────────────────────────────

def fmt_money(val):
    if not val: return "无限制"
    if val >= 1e8: return f"{val/1e8:.0f}亿"
    if val >= 1e4: return f"{val/1e4:.0f}万"
    return f"{val:.0f}元"

def build_wechat_message(rows, now_str):
    """构建微信推送的标题和正文（支持 Server酱 Markdown）"""
    arb = [r for r in rows if (r["premium"] or 0) > 0 and r["status"] in ("open", "limited")]
    all_pos = [r for r in rows if (r["premium"] or 0) > 0]

    title = f"LOF溢价提醒 {now_str}｜{len(arb)}只套利机会"
    if not arb:
        title = f"LOF溢价提醒 {now_str}｜暂无套利机会"

    lines = [f"## LOF 溢价追踪 · {now_str}", ""]

    # 套利机会
    if arb:
        lines.append(f"### ⚡ 套利机会（{len(arb)}只）")
        lines.append("")
        # lines.append("| 基金 | 溢价 | 限额 | 状态 |")
        # lines.append("|------|------|------|------|")
        for r in arb:
            lines.append(
                f"| {r['name']} `{r['full_code']}` "
                f"| **+{r['premium']:.2f}%** "
                f"| {fmt_money(r['quota'])} "
                f"| {r['status_text']} |"
            )
        lines.append("")
    else:
        lines.append("### 暂无套利机会")
        lines.append("")

    # # 所有溢价基金（含暂停申购的）
    # if all_pos:
    #     closed_pos = [r for r in all_pos if r["status"] not in ("open", "limited")]
    #     if closed_pos:
    #         lines.append(f"### ⚠️ 溢价但已暂停申购（{len(closed_pos)}只）")
    #         lines.append("")
    #         for r in closed_pos:
    #             lines.append(f"- {r['name']} `{r['full_code']}` 溢价 **+{r['premium']:.2f}%** · {r['status_text']}")
    #         lines.append("")

    # # 全部排名（折叠展示前10）
    # lines.append("### 📊 溢价率排行（前10）")
    # lines.append("")
    # lines.append("| 排名 | 基金 | 溢价率 | 限额 |")
    # lines.append("|------|------|--------|------|")
    # for i, r in enumerate(rows[:10], 1):
    #     prem = r["premium"]
    #     prem_str = f"+{prem:.2f}%" if prem and prem > 0 else (f"{prem:.2f}%" if prem else "—")
    #     lines.append(f"| {i} | {r['name']} | {prem_str} | {fmt_money(r['quota'])} |")

    # lines.append("")
    # lines.append(f"---")
    # lines.append(f"*数据来源：palmmicro + 天天基金 · {now_str}*")

    return title, "\n".join(lines)

# ─── Server酱推送 ─────────────────────────────────────────────────────────────

def send_wechat(title, content, sendkey):
    """通过 Server酱 推送微信消息"""
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    try:
        r = requests.post(url, data={
            "title": title,
            "desp": content,
        }, timeout=15)
        result = r.json()
        if result.get("code") == 0:
            print(f"✅ 微信推送成功")
        else:
            print(f"⚠️  推送失败: {result}")
    except Exception as e:
        print(f"❌ 推送异常: {e}")

def generate_orders(rows, premium_threshold=0.5, order_type=">"):
    """
    生成LOF申购订单字符串
    
    参数：
        rows: 基金数据列表（包含code6, quota, premium, status等字段）
        premium_threshold: 溢价率阈值（%），超过此值的基金将被列入订单
        order_type: 订单类型，">" 拖拉机申购，"$" 单账户申购
    
    返回：
        订单内容字符串，每行格式为 ">基金代码:申购限额"
    """
    # 过滤出有套利价值且可申购的基金
    eligible = [
        r for r in rows 
        if (r["premium"] or 0) > premium_threshold 
        and r["status"] in ("open", "limited")
    ]
    
    lines = []
    
    if not eligible:
        lines.append("# 暂无符合条件的套利机会")
    else:
        # 按溢价率降序排序
        eligible.sort(key=lambda x: x["premium"], reverse=True)
        for r in eligible:
            # 确定申购限额（如果有大额限购，使用限购额度；否则使用默认值）
            quota = r["quota"]
            if quota:
                # 将限额转换为整数金额（单位：元）
                order_amount = int(quota) if quota < 1e4 else int(quota / 1e4) * 10000
            else:
                order_amount = 1000  # 默认1万元

            if order_amount > 10000:
                order_amount = 10000
            lines.append("# %s - 溢价率: +%.2f%%" % (r["name"], r["premium"]))
            lines.append("%s%s:%d" % (order_type, r["code6"], order_amount))
    
    return "\n".join(lines)

def save_history_csv(rows, now_str, filepath="history.csv"):
    """追加一行到历史CSV"""
    file_exists = os.path.exists(filepath)
    with open(filepath, "a", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["时间"] + [r["full_code"] for r in rows]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        row = {"时间": now_str}
        for r in rows:
            row[r["full_code"]] = r["premium"] if r["premium"] is not None else ""
        writer.writerow(row)
    print(f"历史记录已追加到 {filepath}")

WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=d68e5beb-9b8f-4d76-8006-8f58dd50c6b2"
def send_notification(msg):
    print("[开始发送企业微信推送]...\n%s" % msg)
    
    # 企业微信机器人支持 Markdown 格式
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": msg
        }
    }
    
    try:
        # 直接 POST 到 Webhook 地址，发送 JSON 数据
        res = requests.post(WEBHOOK_URL, json=payload, timeout=10).json()
        if res.get("errcode") == 0:
            print("推送成功")
        else:
            print("返回错误: %s" % res)
    except Exception as e:
        print("推送失败，网络异常: %s" % e)

# ─── 主程序 ──────────────────────────────────────────────────────────────────

def main():
    # Server酱 SendKey 从环境变量读取（GitHub Actions Secret）
    sendkey = os.environ.get("SERVERCHAN_KEY", "")
    if not sendkey:
        print("⚠️  未设置 SERVERCHAN_KEY 环境变量，将跳过微信推送")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== LOF溢价监控 {now_str} ===")

    premium_map = fetch_premium()
    time.sleep(0.5)
    price_map = fetch_prices()
    time.sleep(0.5)
    quota_map = fetch_quota()

    rows = merge(premium_map, price_map, quota_map)

    # 保存历史 CSV
    save_history_csv(rows, now_str)

    send_wechat(generate_orders(rows, premium_threshold=0.5, order_type=">"))

    # 构建并发送微信消息
    title, content = build_wechat_message(rows, now_str)
    print(f"\n--- 推送内容预览 ---\n{title}\n")

    print(content)
    
    send_notification(content)
    
    if sendkey:
        send_wechat(title, content, sendkey)

if __name__ == "__main__":
    main()
