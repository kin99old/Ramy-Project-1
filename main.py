
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

# --- متغيرات البيئة ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')          # القناة الأولى
CHAT_ID_2 = os.environ.get('CHAT_ID_2')      # القناة الثانية (الجديدة)
SECRET_KEY = os.environ.get('SECRET_KEY')

# --- حفظ آخر رسالة ---
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
        caption = "👇 TO COPY TRADES 👇\nhttps://t.me/Kin99old/768"
        send_telegram_photo(img_buffer, caption)
        return JSONResponse(content={"status": "✅ Report sent successfully"})
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        send_telegram_message(f"⚠️ Report Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# --- وظائف مساعدة ---
def parse_html_content(html_content):
    clean_text = re.sub('<[^<]+?>', '', html_content)
    clean_text = ' '.join(clean_text.split())
    
    # تحديد نوع التقرير
    period = "Custom"
    
    # البحث عن نوع التقرير الجديد
    if "REPORT (DAILY)" in clean_text:
        period = "Daily"
    elif "REPORT (WEEKLY)" in clean_text:
        period = "Weekly"
    elif "REPORT (MONTHLY)" in clean_text:
        period = "Monthly"
    else:
        # إذا لم يكن من الأنواع الجديدة، نبحث عن عدد الساعات القديم
        period_match = re.search(r'REPORT\s*\((\d+)\s*hours?\)', clean_text)
        if period_match:
            hours = int(period_match.group(1))
            if hours == 24:
                period = "Daily"
            elif 120 <= hours <= 168:
                period = "Weekly"
            elif 480 <= hours <= 744:
                period = "Monthly"
            else:
                period = f"{hours} hours"

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

    # إعداد الألوان
    bg_color = '#111827'         # خلفية داكنة أكثر احترافية
    text_color = '#F9FAFB'       # أبيض ناعم
    accent_color = '#22D3EE'     # لون مميز للعنوانين
    card_bg = '#1F2937'          # لون خلفية البطاقات

    fig = plt.gcf()
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    # --- عنوان التقرير ---
    report_title = {
        'Daily': "Daily Trading Report",
        'Weekly': "Weekly Trading Report",
        'Monthly': "Monthly Trading Report"
    }.get(report_data['period'], "Trading Report")

    plt.text(0.5, 0.92, report_title, fontsize=26, fontweight='bold',
             color=accent_color, ha='center', fontfamily='sans-serif', transform=ax.transAxes)

    # --- بطاقة الإحصائيات (كروت) ---
    stats = {
        "Total Trades": report_data['total_trades'],
        "Winning Trades": report_data['winning_trades'],
        "Losing Trades": report_data['losing_trades'],
        "Win Rate": f"{report_data['win_rate']:.1f}%",
        "Net Profit": f"{report_data['net_pips']:+,.1f} pips"
    }

    y_start = 0.75
    spacing = 0.12
    for i, (label, value) in enumerate(stats.items()):
        y = y_start - i * spacing
        ax.add_patch(plt.Rectangle((0.1, y - 0.05), 0.8, 0.09, color=card_bg, transform=ax.transAxes, zorder=1))
        plt.text(0.12, y, label, fontsize=14, color=accent_color, fontweight='bold',
                 transform=ax.transAxes, ha='left', va='center')
        plt.text(0.88, y, str(value), fontsize=16, color=text_color, fontweight='bold',
                 transform=ax.transAxes, ha='right', va='center')

    # --- شعار أو علامة مائية ---
    try:
        logo = plt.imread('logo.png')
        ax.imshow(logo, extent=[0.4, 0.6, 0.35, 0.45], aspect='auto', alpha=0.22, zorder=10)
    except Exception as e:
        logger.warning(f"Logo error: {str(e)}")
        plt.text(0.5, 0.32, "@kin99old", fontsize=80, color='#ffffff08', ha='center', rotation=25, transform=ax.transAxes)

    # --- تذييل التقرير ---
    plt.text(0.5, 0.07, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}", 
             fontsize=10, color='#9CA3AF', ha='center', transform=ax.transAxes)
    plt.text(0.5, 0.03, "© kin99old Report", fontsize=10, color='#9CA3AF', ha='center', transform=ax.transAxes)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf


def send_telegram_photo(image_buffer, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    files = {'photo': ('report.png', image_buffer.getvalue(), 'image/png')}
    
    # إرسال إلى القناة الأولى
    data = {'chat_id': CHAT_ID, 'caption': caption}
    requests.post(url, files=files, data=data, timeout=10)
    
    # إرسال إلى القناة الثانية
    data = {'chat_id': CHAT_ID_2, 'caption': caption}
    requests.post(url, files=files, data=data, timeout=10)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # إرسال إلى القناة الأولى
    data = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    requests.post(url, data=data, timeout=5)
    
    # إرسال إلى القناة الثانية
    data = {'chat_id': CHAT_ID_2, 'text': text, 'parse_mode': 'HTML'}
    requests.post(url, data=data, timeout=5)
