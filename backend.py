from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import mplfinance as mpf
import yfinance as yf
import os
import io
import base64
import plotly.graph_objs as go
import plotly.io as pio
from datetime import datetime, timedelta
import mysql.connector
from openai import OpenAI
import requests

app = Flask(__name__)

app.secret_key = os.urandom(98)

sector_to_etf = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Consumer Cyclical": "XLY",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Utilities": "XLU",
    "Consumer Defensive": "XLP",
    "Real Estate": "XLRE",
    "Materials": "XLB",
    "Communication Services": "XLC"
}

"""
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",  
        database="finance_project"
    )
"""

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,  
        database=DB
    )

def get_items():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user_items WHERE login_name = %s;", (session['username'],))
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    return items or []

@app.route('/login_page')
def login_page():
    return render_template("login_page.html")

@app.route('/signup_page')
def signup_page():
    return render_template("signup_page.html")

@app.route('/submit_signup', methods=["POST"])
def signup():
    username = request.form.get("username")
    password = request.form.get("password")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.callproc('proc_register_user', [username, password])
    conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for('home'))

@app.route('/submit_login', methods=["POST"])
def verify_login():
    username = request.form.get("username")
    password = request.form.get("password")

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT sfn_validate_user(%s, %s)"
    cursor.execute(query, (username, password))
    (result,) = cursor.fetchone()
    cursor.close()
    conn.close()

    if result:
        session['logged_in'] = True
        session['username'] = username
        return redirect(url_for('home'))
    else:
        return redirect(url_for("login_page"))
    
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

def plot_graph(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period='6mo')

    fig = go.Figure(
        data = go.Scatter(x=hist.index, y = hist['Close'], mode='lines'),
        layout=go.Layout(
            dragmode=False, 
            xaxis=dict(fixedrange=True, tickfont=dict(size=10)),
            yaxis=dict(fixedrange=True, tickfont=dict(size=10)),
            margin=dict(l=0, r=0, t=0, b=0),
            width=300,
            height=200
    ))
    return pio.to_html(fig, full_html=False, include_plotlyjs=True, config={'displayModeBar': False})
    
@app.route("/")
def home():
    if session.get('logged_in', False):
        return render_template('home_page.html', logged_in=True, items=get_items())
    else:
        return render_template('home_page.html', logged_in=False, items=[])

@app.route('/submit_investment_out', methods=['POST'])
def submit_investiment_out():
    data = request.get_json()
    investment_id = data.get("investment_id")

    plot_html = plot_graph(investment_id)

    stock = yf.Ticker(investment_id)
    current_price = stock.info["currentPrice"]
    previous_close = stock.info["previousClose"]
    percent_change = ((current_price - previous_close) / previous_close) * 100
    market_cap = stock.info.get("marketCap")
    pe_ratio = stock.info.get("trailingPE")

    sector = stock.info.get("sector")
    etf_symbol = sector_to_etf.get(sector)
    etf = yf.Ticker(etf_symbol)
    etf_name = etf.info.get('longName')
    etf_market_cap = etf.info.get('marketCap')
    etf_pe = etf.info.get('trailingPE')
    etf_change = etf.info.get('regularMarketChangePercent')

    today = datetime.today().strftime('%Y-%m-%d')
    month_ago = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%d')

    news_url = (f'https://newsapi.org/v2/everything?'
                f'q={investment_id}&'
                f'from_param={month_ago}&'
                f'to={today}'
                f'sortBy=popularity&'
                f'language=en&'
                f'pageSize=15&'
                f'apiKey={os.getenv("NEWS_API_KEY")}')
    
    response = requests.get(news_url)
    data = response.json()
    top_descriptions = [article["description"] for article in data.get("articles", [])[:15]]

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Give me a 2 sentence analysis of the stock with the ticker {investment_id}. Use up to date information in your analysis from {top_descriptions}. Focus on news that is affecting the stock price and most generally relevant. Avoid em dashes."}
        ],
    )

    sentiment = response.choices[0].message.content

    return jsonify({
        "plot_html": plot_html,
        "info": {
            "current_price": current_price,
            "percent_change": percent_change,
            "market_cap": market_cap,
            "pe_ratio": pe_ratio,
            "etf_name": etf_name,
            "etf_symbol": etf_symbol,
            "etf_market_cap": etf_market_cap,
            "etf_pe": etf_pe,
            "etf_change": etf_change,
            "sentiment": sentiment
        }
    })

@app.route('/submit_investment_in', methods=['POST'])
def submit_investiment_in():
    conn = get_db_connection()
    cursor = conn.cursor()
    data = request.get_json()
    investment_id = data.get("investment_id")

    cursor.execute("INSERT INTO user_items (login_name, item_text) VALUES (%s, %s)", (session['username'], investment_id))
    conn.commit()

    cursor.close()
    conn.close()
    return {"status": "success"}, 200

@app.route('/delete_investment', methods=['POST'])
def delete_investment():
    if session.get('logged_in', False):
        data = request.get_json()
        investment_id = data.get('investment_id')
        username = session['username']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_items WHERE item_text = %s AND login_name = %s", (investment_id, username))
        conn.commit()
        cursor.close()
        conn.close()

    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)