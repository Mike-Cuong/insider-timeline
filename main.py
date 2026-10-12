import streamlit as st
import pandas as pd
from edgar import Company, set_identity

# The SEC requires an email to access their free data
set_identity("10426726@student.vgu.edu.vn")

st.title("Insider Activity Timeline Analyzer")

ticker = st.text_input("Enter a Stock Ticker (e.g., TSLA, AAPL):").upper()

if ticker:
    st.write(f"Fetching recent insider trades for {ticker}...")
    try:
        company = Company(ticker)
        filings = company.get_filings(form="4").head(30) # Get last 30 filings
        
        trades = []
        for filing in filings:
            summary = filing.obj().get_ownership_summary()
            if summary.net_value: # Filter out grants to focus on real buys/sells
                direction = "Buy" if summary.net_change > 0 else "Sell"
                trades.append({
                    "Date": filing.filing_date,
                    "Insider": summary.insider_name,
                    "Action": direction,
                    "Shares": abs(summary.net_change),
                    "Value ($)": abs(summary.net_value)
                })
        
        df = pd.DataFrame(trades)
        
        if not df.empty:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date')
            
            # Display data table
            st.dataframe(df)
            
            # Display visual timeline chart
            st.subheader("Transaction Volume Timeline")
            chart_data = df.set_index('Date')[['Value ($)']]
            st.bar_chart(chart_data)
        else:
            st.warning("No actionable insider trades found for this ticker.")
    except Exception as e:
        st.error("Could not fetch data. Please check the ticker symbol.")
