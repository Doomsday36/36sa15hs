import streamlit as st
import pandas as pd
from pathlib import Path
from kiteconnect import KiteConnect
import webbrowser
import sqlite3
from datetime import datetime, time as dt_time
from urllib.parse import urlencode

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='GDP dashboard',
    page_icon=':earth_americas:', # This is an emoji shortcode. Could be a URL too.
)

# -----------------------------------------------------------------------------
# Declare some useful functions.

@st.cache_data
def get_gdp_data():
    """Grab GDP data from a CSV file.

    This uses caching to avoid having to read the file every time. If we were
    reading from an HTTP endpoint instead of a file, it's a good idea to set
    a maximum age to the cache with the TTL argument: @st.cache_data(ttl='1d')
    """

    # Instead of a CSV on disk, you could read from an HTTP endpoint here too.
    DATA_FILENAME = Path(__file__).parent/'data/gdp_data.csv'
    raw_gdp_df = pd.read_csv(DATA_FILENAME)

    MIN_YEAR = 1960
    MAX_YEAR = 2022
    gdp_df = raw_gdp_df.melt(
        ['Country Code'],
        [str(x) for x in range(MIN_YEAR, MAX_YEAR + 1)],
        'Year',
        'GDP',
    )
    gdp_df['Year'] = pd.to_numeric(gdp_df['Year'])

    return gdp_df

gdp_df = get_gdp_data()

# -----------------------------------------------------------------------------
# OAuth Setup

API_KEY = 'your_api_key'         # Replace with your API Key
API_SECRET = 'your_api_secret'   # Replace with your API Secret
REDIRECT_URL = 'https://36sa15hs.streamlit.app/?'

kite = KiteConnect(api_key=API_KEY)

def get_access_token(request_token):
    try:
        data = kite.generate_session(request_token, api_secret=API_SECRET)
        kite.set_access_token(data["access_token"])
        st.session_state['access_token'] = data["access_token"]
        st.success("Authentication successful!")
    except Exception as e:
        st.error(f"Error generating session: {e}")

def get_login_url():
    return kite.login_url()

# Authentication handling
if 'access_token' not in st.session_state:
    # Display login button
    st.sidebar.header("Login to Zerodha Kite")
    login_url = get_login_url()
    st.sidebar.markdown(f"[Login]({login_url}) to access trading features.")
    
    # Check if redirected back with request_token
    query_params = st.experimental_get_query_params()
    if 'request_token' in query_params:
        request_token = query_params['request_token'][0]
        get_access_token(request_token)
else:
    st.sidebar.success("You are logged in!")


# -----------------------------------------------------------------------------
# Trading Signals Logic

def fetch_candle_data(kite, instrument_token, date, interval="15minute"):
    try:
        to_date = date + pd.Timedelta(minutes=15)
        data = kite.historical_data(
            instrument_token=instrument_token,
            from_date=date.strftime("%Y-%m-%d %H:%M"),
            to_date=to_date.strftime("%Y-%m-%d %H:%M"),
            interval=interval
        )
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error fetching candle data: {e}")
        return pd.DataFrame()

def check_conditions(df):
    if df.empty:
        return "No Data"

    open_price = df["open"].iloc[0]
    high_price = df["high"].iloc[0]
    low_price = df["low"].iloc[0]
    prev_close = df["close"].iloc[-1]  # Assuming last close is previous close

    # Define your conditions
    if open_price == low_price and prev_close == open_price:
        return "BUY"
    elif open_price == low_price:
        return "BUY"
    elif prev_close == high_price:
        return "SELL"
    elif open_price == high_price:
        return "SELL"
    elif prev_close == open_price and open_price == high_price:
        return "SELL"
    elif low_price == prev_close:
        return "BUY"
    else:
        return "HOLD"

def record_signal(signal):
    conn = sqlite3.connect('trade_signals.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS signals 
                 (timestamp TEXT, signal TEXT)''')
    c.execute("INSERT INTO signals VALUES (?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), signal))
    conn.commit()
    conn.close()


if 'access_token' in st.session_state:
    st.header("Trading Signals")
    
    # Input fields
    instrument_token = st.text_input("Instrument Token", value="your_instrument_token")  # Replace with actual token
    date_input = st.date_input("Date for Candle", value=datetime.today())
    time_input = st.time_input("Time for Candle", value=dt_time(9, 30))  # Default to 9:30 AM
    
    # Combine date and time
    candle_datetime = datetime.combine(date_input, time_input)
    
    if st.button("Check Signal"):
        with st.spinner("Fetching candle data..."):
            df = fetch_candle_data(kite, instrument_token, candle_datetime)
            signal = check_conditions(df)
            record_signal(signal)
            st.success(f"Signal: {signal}")
    
    # Display the signal history
    st.subheader("Signal History")
    conn = sqlite3.connect('trade_signals.db')
    history_df = pd.read_sql("SELECT * FROM signals", conn)
    conn.close()
    st.dataframe(history_df)

# -----------------------------------------------------------------------------
# Draw the actual page

min_value = gdp_df['Year'].min()
max_value = gdp_df['Year'].max()

from_year, to_year = st.slider(
    'Which years are you interested in?',
    min_value=min_value,
    max_value=max_value,
    value=[min_value, max_value])

countries = gdp_df['Country Code'].unique()

if not len(countries):
    st.warning("Select at least one country")

selected_countries = st.multiselect(
    'Which countries would you like to view?',
    countries,
    ['DEU', 'FRA', 'GBR', 'BRA', 'MEX', 'JPN'])

''
''
''

# Filter the data
filtered_gdp_df = gdp_df[
    (gdp_df['Country Code'].isin(selected_countries))
    & (gdp_df['Year'] <= to_year)
    & (from_year <= gdp_df['Year'])
]

st.header('GDP over time', divider='gray')

''

st.line_chart(
    filtered_gdp_df,
    x='Year',
    y='GDP',
    color='Country Code',
)

''
''


first_year = gdp_df[gdp_df['Year'] == from_year]
last_year = gdp_df[gdp_df['Year'] == to_year]

st.header(f'GDP in {to_year}', divider='gray')

''

cols = st.columns(4)

for i, country in enumerate(selected_countries):
    col = cols[i % len(cols)]

    with col:
        first_gdp = first_year[first_year['Country Code'] == country]['GDP'].iat[0] / 1000000000
        last_gdp = last_year[last_year['Country Code'] == country]['GDP'].iat[0] / 1000000000

        if math.isnan(first_gdp):
            growth = 'n/a'
            delta_color = 'off'
        else:
            growth = f'{last_gdp / first_gdp:,.2f}x'
            delta_color = 'normal'

        st.metric(
            label=f'{country} GDP',
            value=f'{last_gdp:,.0f}B',
            delta=growth,
            delta_color=delta_color
        )
