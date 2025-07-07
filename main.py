from fastapi import FastAPI, Request, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse
import os
from datetime import datetime
import logging
import matplotlib.pyplot as plt
import io
import re
import requests

app = FastAPI()
logger = logging.getLogger("uvicorn")
logging.basicConfig(level=logging.INFO)

# البيئة
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
SECRET_KEY = os.environ.get('SECRET_KEY')

# حفظ آخر رسالة
last_data = {}

# ✅ POST - استقبال من TradingView
@app.post("/send")
async def send_post(request: Request):
    global last_data
    data = await request.json()

    if data.get("secret") != SECRET_KEY:
        return {"status": "❌ Secret غير صحيح"}

    data["time"] = datetime.utcnow().isoformat()
    last_data = data

    return {"status": "✅ تم الاستلام بدون إرسال إلى Telegram"}

# ✅ GET - جلب آخر رسالة
@app.get("/last")
async def get_last_data():
    return last_data

# ✅ POST - رفع تقرير HTML وتحويله لصورة
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), x_secret_key: str = Header(None)):
    if x_secret_key != SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        content = (await file.read()).decode('utf-8')
        report_data = parse_html_content(content)
        img_buffer = generate_report_image(report_data)
        caption = "👇 لنسخ الصفقات 👇\nhttps://t.me/Kin99old/768"
        send_telegram_photo(img_buffer, caption)
        return JSONResponse(content={"status": "✅ Report sent successfully"})
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        send_telegram_message(f"⚠️ Report Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ✅ وظائف مساعدة
def parse_html_content(html_content):
    clean_text = re.sub('<[^<]+?>', '', html_content)
    clean_text = ' '.join(clean_text.split())
    period = "1 hour"
    period_match = re.search(r'Daily Report \((\d+) hours?\)', clean_text)
    if period_match:
        period = f"{period_match.group(1)} hours"
    total_pips = 0.0
    trades = []
    for match in re.finditer(r'Order\s*#(\d+):\s*(BUY|SELL)\s+(\w+)\s*\|\s*Profit:\s*(-?[\d.]+)\s*pips', clean_text):
        pips = float(match.group(4))
        total_pips += pips
        trades.append({'order_id': match.group(1), 'type': match.group(2), 'symbol': match.group(3), 'profit_pips': pips})
    winning_trades = int(re.search(r'Winning Trades:\s*(\d+)', clean_text).group(1))
    losing_trades = int(re.search(r'Losing Trades:\s*(\d+)', clean_text).group(1))
    total_trades = winning_trades + losing_trades
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    net_profit_match = re.search(r'Net Profit:\s*(-?[\d.]+)\s*pips', clean_text)
    if net_profit_match:
        total_pips = float(net_profit_match.group(1))
    return {
        'period': period,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'net_pips': total_pips,
        'trades': trades
    }

def generate_report_image(report_data):
    plt.figure(figsize=(12, 8))
    ax = plt.gca()
    ax.axis('off')
    bg_color = '#1a1a2e'
    text_color = '#e6e6e6'
    accent_color = '#4cc9f0'
    fig = plt.gcf()
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    plt.text(0.5, 0.95, "Kin99old_copytrading Report", fontsize=24, fontweight='bold',
             color=accent_color, fontfamily='sans-serif', horizontalalignment='center', transform=ax.transAxes)
    plt.text(0.5, 0.5, "@kin99old", fontsize=120, color='#ffffff10',
             fontweight='bold', fontfamily='sans-serif', horizontalalignment='center',
             verticalalignment='center', rotation=30, transform=ax.transAxes)
    content = [
        f"Reporting Period: {report_data['period']}",
        "",
        f"Total Trades: {report_data['total_trades']}",
        f"Winning Trades: {report_data['winning_trades']}",
        f"Losing Trades: {report_data['losing_trades']}",
        f"Win Rate: {report_data['win_rate']:.1f}%",
        f"Net Profit: {report_data['net_pips']:+,.1f} pips",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "© Kin99old_copytrading Report"
    ]
    plt.text(0.1, 0.85, '\n'.join(content), fontsize=16, color=text_color,
             fontfamily='sans-serif', verticalalignment='top', linespacing=1.8)
    for x, y, text, size in [
        (0.8, 0.75, f"Net Profit: {report_data['net_pips']:+,.1f} pips", 20),
        (0.8, 0.7, f"Win Rate: {report_data['win_rate']:.1f}%", 20)
    ]:
        plt.text(x, y, text, fontsize=size, fontweight='bold', color=accent_color,
                 fontfamily='sans-serif', horizontalalignment='center', transform=ax.transAxes)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def send_telegram_photo(image_buffer, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    files = {'photo': ('report.png', image_buffer.getvalue(), 'image/png')}
    data = {'chat_id': CHAT_ID, 'caption': caption}
    requests.post(url, files=files, data=data, timeout=10)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    requests.post(url, data=data, timeout=5)
