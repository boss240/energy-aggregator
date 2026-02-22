from fastapi import FastAPI, HTTPException
from entsoe import EntsoePandasClient
import pandas as pd
from datetime import timedelta
import os

# Створюємо наш API додаток
app = FastAPI(title="EC GRID API")

# Головна сторінка (просто для перевірки, що сервер живий)
@app.get("/")
def read_root():
    return {"message": "⚡ EC GRID API успішно працює! Готовий віддавати дані мобільному додатку."}

# Ендпоінт для отримання цін РДН
@app.get("/api/market/{country_code}")
def get_market_data(country_code: str):
    api_key = os.environ.get("entsoe_key")
    if not api_key:
        raise HTTPException(status_code=500, detail="Ключ ENTSO-E не знайдено на сервері")

    client = EntsoePandasClient(api_key=api_key)
    now = pd.Timestamp.now(tz='Europe/Kyiv')
    start = now - timedelta(hours=24)
    end = now + timedelta(hours=24)

    try:
        # Отримуємо ціни
        prices = client.query_day_ahead_prices(country_code, start=start, end=end)
        
        # Знаходимо поточну ціну
        current_price = float(prices.asof(now)) if not prices.empty else 0.0

        # Віддаємо чисті дані для майбутнього iPhone-додатка
        return {
            "zone": country_code,
            "current_spot_price_eur": round(current_price, 2),
            "timestamp": now.strftime('%Y-%m-%d %H:%M:%S'),
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка ENTSO-E: {str(e)}")
