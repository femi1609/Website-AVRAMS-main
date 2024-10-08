import streamlit as st
import pandas as pd
import pickle
import numpy as np
import re
from sklearn.impute import KNNImputer
import plotly.express as px
import plotly.graph_objects as go

# Load model, encoders, and scaler
with open('label_encoders.pkl', 'rb') as f:
    label_encoders = pickle.load(f)

with open('scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

with open('random_forest_model.pkl', 'rb') as f:
    model_top = pickle.load(f)

st.write(f"Model type: {type(model_top)}")

# Define feature mapping and top features
top_features = ['Vendor Name Encoded', 'CVE ID Encoded', 'CWE Encoded', 'Composite Risk Score']

weights = {
    'Base Score': 0.20,
    'Exploitability Score': 0.25,
    'Impact Score': 0.20,
    'Age': 0.10,
    'Update Lag': 0.10
}

# Helper function to safely encode categorical data
def safe_label_encode(encoder, value, default=-1):
    try:
        return encoder.transform([value])[0]
    except ValueError:
        return default

def preprocess_data_csv(df):
    # Drop duplicates
    df = df.drop_duplicates()

    # Strip whitespace
    df['Description'] = df['Description'].str.strip()
    df['Vendor Name'] = df['Vendor Name'].str.strip()

    # Replace invalid categories with NaN
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    df['Vulnerability Category'] = df['Vulnerability Category'].apply(lambda x: np.nan if isinstance(x, str) and re.search(url_pattern, x) else x)

    df['CWE'] = df['CWE'].apply(lambda x: np.nan if isinstance(x, str) and re.search(url_pattern, x) else x)

    # Handle date formats and NaN values
    df['Publish Date'] = pd.to_datetime(df['Publish Date'], errors='coerce')
    df['Update Date'] = pd.to_datetime(df['Update Date'], errors='coerce')
    
    df['EPSS Score'] = df['EPSS Score'].str.rstrip('%').astype('float') / 100.0

    # Handle numeric columns
    numeric_columns = [
        'Max CVSS Base Score',
        'Exploitability Score',
        'Impact Score',
        'Base Score',
        'EPSS Score'
    ]
    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce')
    
    # Impute missing values in numeric columns
    imputer = KNNImputer(n_neighbors=5)
    df[numeric_columns] = imputer.fit_transform(df[numeric_columns])
    
    return df

def preprocess_data_manual(df):
    # Drop duplicates
    df = df.drop_duplicates()

    # Strip whitespace
    df['Vendor Name'] = df['Vendor Name'].str.strip()

    # Remove URLs from 'CWE'
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    df['CWE'] = df['CWE'].apply(lambda x: np.nan if isinstance(x, str) and re.search(url_pattern, x) else x)

    # Handle date formats
    df['Publish Date'] = pd.to_datetime(df['Publish Date'], errors='coerce')
    df['Update Date'] = pd.to_datetime(df['Update Date'], errors='coerce')

    # Calculate Age and Update Lag
    df['Age'] = (pd.to_datetime('today') - df['Publish Date']).dt.days
    df['Update Lag'] = (df['Update Date'] - df['Publish Date']).dt.days

    # Fill NaNs in Age and Update Lag columns
    df['Age'] = df['Age'].fillna(0)
    df['Update Lag'] = df['Update Lag'].fillna(0)
    
    # Handle numeric columns
    numeric_columns = [
        'Exploitability Score',
        'Impact Score',
        'Base Score'
       # 'EPSS Score'
    ]
    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce')
    
    # Impute missing values in numeric columns
    imputer = KNNImputer(n_neighbors=5)
    df[numeric_columns] = imputer.fit_transform(df[numeric_columns])
    
    return df

st.title("Vulnerability Risk Assessment")

input_method = st.radio("Select input method:", ("Manual Input", "CSV Upload"))

if input_method == "Manual Input":
    num_entries = st.number_input("Number of entries (up to 1000):", min_value=1, max_value=1000)

    user_data_list = []
    
    for i in range(num_entries):
        with st.expander(f"Entry {i + 1}"):
            cve_id = st.text_input(f'CVE ID {i + 1}')
            vendor_name = st.text_input(f'Vendor Name {i + 1}')
            cwe = st.text_input(f'CWE {i + 1}')
            base_score = st.number_input(f'Base Score {i + 1}', format="%.2f", step=0.01)
            exploitability_score = st.number_input(f'Exploitability Score {i + 1}', format="%.2f", step=0.01)
            impact_score = st.number_input(f'Impact Score {i + 1}', format="%.2f", step=0.01)
            publish_date = st.date_input(f'Publish Date {i + 1}')
            update_date = st.date_input(f'Update Date {i + 1}')

            if st.button(f"Add Entry {i + 1}"):
                # Create a DataFrame for input
                data = {
                    'CVE ID': [cve_id],
                    'Vendor Name': [vendor_name],
                    'CWE': [cwe],
                    'Base Score': [float(base_score)],
                    'Exploitability Score': [float(exploitability_score)],
                    'Impact Score': [float(impact_score)],
                    'Publish Date': [publish_date],
                    'Update Date': [update_date]
                }
                df = pd.DataFrame(data)

                # Preprocess the DataFrame
                df = preprocess_data_manual(df)

                # Calculate Age and Update Lag
                df['Age'] = (pd.to_datetime('today') - pd.to_datetime(df['Publish Date'])).dt.days
                df['Update Lag'] = (pd.to_datetime(df['Update Date']) - pd.to_datetime(df['Publish Date'])).dt.days

                # Calculate Composite Risk Score
                df['Composite Risk Score'] = df[['Base Score', 'Exploitability Score', 'Impact Score', 'Age', 'Update Lag']].apply(
                    lambda x: sum(weights[col] * x[col] for col in weights.keys()), axis=1
                )

                # Normalize Composite Risk Score
                df[['Composite Risk Score']] = scaler.transform(df[['Composite Risk Score']])

                # Encode categorical columns
                df['Vendor Name Encoded'] = df['Vendor Name'].apply(lambda x: safe_label_encode(label_encoders['Vendor Name'], x))
                df['CVE ID Encoded'] = df['CVE ID'].apply(lambda x: safe_label_encode(label_encoders['CVE ID'], x))
                df['CWE Encoded'] = df['CWE'].apply(lambda x: safe_label_encode(label_encoders['CWE'], x))

                # Prepare features for prediction
                X_new = df[top_features].values
                # Check for missing values in the DataFrame
                if df[top_features].isnull().any().any():
                    st.error("Error: There are missing values in the input features. Please clean the data before prediction.")
                else:
                    # Check shape of the features
                    st.write(f"Shape of input features for prediction: {X_new.shape}")

                    # Predict EPSS score using the model
                    try:
                        df['Predicted EPSS Score'] = model_top.predict(X_new)
                    except Exception as e:
                        st.error(f"Prediction failed: {str(e)}")

                # Predict EPSS score using the model
                df['Predicted EPSS Score'] = model_top.predict(X_new)

                # Rank vulnerabilities based on predicted EPSS score
                df['Rank'] = df['Predicted EPSS Score'].rank(ascending=False, method='first')
                df = df.sort_values(by='Rank').reset_index(drop=True)
                df['Rank'] = df.index + 1

                # Risk assessment based on EPSS score
                def risk_assessment(likelihood):
                    if likelihood >= 0.9:
                        return 'Critical', 'Immediate Patching', '24 hours'
                    elif 0.7 <= likelihood < 0.9:
                        return 'High', 'Priority Patching', '48 hours'
                    elif 0.4 <= likelihood < 0.7:
                        return 'Medium', 'Scheduled Patching', '7 days'
                    else:
                        return 'Low', 'Monitor', '30 days'

                df[['Risk Level', 'Suggested Action', 'Timeline']] = df['Predicted EPSS Score'].apply(risk_assessment).apply(pd.Series)

                # Keep only specified columns
                df = df[['CVE ID', 'Vendor Name', 'CWE', 'Composite Risk Score', 'Predicted EPSS Score', 'Rank', 'Risk Level', 'Suggested Action', 'Timeline']]
                
                user_data_list.append(df)

    if user_data_list:
        combined_df = pd.concat(user_data_list, ignore_index=True)
        st.write("### Results")
        st.dataframe(combined_df)

elif input_method == "CSV Upload":
    uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)

        # Preprocess the CSV data
        df = preprocess_data_csv(df)

        # Calculate Age and Update Lag
        df['Age'] = (pd.to_datetime('today') - df['Publish Date']).dt.days
        df['Update Lag'] = (df['Update Date'] - df['Publish Date']).dt.days

        # Calculate Composite Risk Score
        df['Composite Risk Score'] = df[['Base Score', 'Exploitability Score', 'Impact Score', 'Age', 'Update Lag']].apply(
            lambda x: sum(weights[col] * x[col] for col in weights.keys()), axis=1
        )

        # Normalize Composite Risk Score
        df[['Composite Risk Score']] = scaler.transform(df[['Composite Risk Score']])

        # Encode categorical columns
        df['Vendor Name Encoded'] = df['Vendor Name'].apply(lambda x: safe_label_encode(label_encoders['Vendor Name'], x))
        df['CVE ID Encoded'] = df['CVE ID'].apply(lambda x: safe_label_encode(label_encoders['CVE ID'], x))
        df['CWE Encoded'] = df['CWE'].apply(lambda x: safe_label_encode(label_encoders['CWE'], x))

        # Prepare features for prediction
        X_new = df[top_features].values

        from sklearn.impute import SimpleImputer

        # Create an imputer to fill missing values
        imputer = SimpleImputer(strategy='mean')  # Choose a suitable strategy
        X_new = imputer.fit_transform(X_new)

        # Predict EPSS score using the model
        df['Predicted EPSS Score'] = model_top.predict(X_new)

        # Rank vulnerabilities based on predicted EPSS score
        df['Rank'] = df['Predicted EPSS Score'].rank(ascending=False, method='first')
        df = df.sort_values(by='Rank').reset_index(drop=True)
        df['Rank'] = df.index + 1

        # Risk assessment based on EPSS score
        def risk_assessment(likelihood):
            if likelihood >= 0.35:
                return 'Critical', 'Immediate Patching', '24 hours'
            elif 0.25 <= likelihood < 0.35:
                return 'High', 'Priority Patching', '48 hours'
            elif 0.15 <= likelihood < 0.25:
                return 'Medium', 'Scheduled Patching', '7 days'
            else:
                return 'Low', 'Monitor', '30 days'

        df[['Risk Level', 'Suggested Action', 'Timeline']] = df['Predicted EPSS Score'].apply(risk_assessment).apply(pd.Series)

        # Keep only specified columns
        df = df[['CVE ID', 'Vendor Name', 'CWE', 'Composite Risk Score', 'Predicted EPSS Score', 'Rank', 'Risk Level', 'Suggested Action', 'Timeline']]

        st.write("### Results")
        st.dataframe(df)
        
        st.title('Prediction Results Dashboard')
        
        # Risk Score Chart
        st.subheader('Risk Score Chart')

        # Sort the DataFrame by Composite Risk Score in descending order
        df_sorted = df.sort_values(by='Composite Risk Score', ascending=False)
        
        # Create the bar chart with the sorted DataFrame
        fig_risk_score = px.bar(df_sorted, x='CVE ID', y='Composite Risk Score', labels={'Composite Risk Score': 'Risk Score'})
        
        # Display the chart
        st.plotly_chart(fig_risk_score)

        # Predicted EPSS Score Chart
        st.subheader('Predicted EPSS Score Chart')
        fig_ep_score = px.line(df, x='CVE ID', y='Predicted EPSS Score', labels={'Predicted EPSS Score': 'EPSS Score'})
        st.plotly_chart(fig_ep_score)
        
        # Risk Level Distribution
        st.subheader('Risk Level Distribution')
        risk_level_counts = df['Risk Level'].value_counts()
        fig_risk_level = px.bar(x=risk_level_counts.index, y=risk_level_counts.values, labels={'x': 'Risk Level', 'y': 'Count'})
        st.plotly_chart(fig_risk_level)
        
        # Top Vendors by Predicted EPSS Score
        st.subheader('Top Vendors by Predicted EPSS Score')
        top_vendors = df.groupby('Vendor Name')['Predicted EPSS Score'].max().sort_values(ascending=False).reset_index()
        fig_top_vendors = px.bar(top_vendors, x='Vendor Name', y='Predicted EPSS Score')
        st.plotly_chart(fig_top_vendors)
        
        # Suggested Actions Breakdown
        st.subheader('Suggested Actions Breakdown')
        action_counts = df['Suggested Action'].value_counts()
        fig_actions = go.Figure(data=[go.Pie(labels=action_counts.index, values=action_counts.values, hole=0.4)])
        st.plotly_chart(fig_actions)
        
        # Risk Level by Vendor
        st.subheader('Risk Level by Vendor')
        risk_level_by_vendor = df.groupby(['Vendor Name', 'Risk Level']).size().unstack(fill_value=0)
        fig_risk_level_vendor = px.bar(risk_level_by_vendor, x=risk_level_by_vendor.index, y=risk_level_by_vendor.columns)
        st.plotly_chart(fig_risk_level_vendor)
        
        
        st.subheader('Risk Score Over Rank')
        
        # Create a line plot of Composite Risk Score over Rank
        fig_line_plot = px.line(df, x='Rank', y='Composite Risk Score', labels={'Composite Risk Score': 'Risk Score', 'Rank': 'Rank'})
        
        # Display the line plot in Streamlit
        st.plotly_chart(fig_line_plot)

        def convert_timeline_to_hours(timeline):
            if 'hour' in timeline:
                return int(timeline.split()[0])
            elif 'day' in timeline:
                return int(timeline.split()[0]) * 24
            return 0

        df['Timeline (Hours)'] = df['Timeline'].apply(convert_timeline_to_hours)
        
        # Streamlit line plot using Timeline (in hours) vs Composite Risk Score
        st.subheader('Composite Risk Score Over Resolution Timeline')
        
        fig_line_plot = px.line(df, x='Timeline (Hours)', y='Composite Risk Score',
                                labels={'Timeline (Hours)': 'Timeline (Hours)', 'Composite Risk Score': 'Risk Score'})
        
        # Display the line plot in Streamlit
        st.plotly_chart(fig_line_plot)
        
        # Optionally, you can create a line plot for Predicted EPSS Score over Timeline (Hours)
        st.subheader('Predicted EPSS Score Over Resolution Timeline')
        
        fig_line_plot_epss = px.line(df, x='Timeline (Hours)', y='Predicted EPSS Score',
                                     labels={'Timeline (Hours)': 'Timeline (Hours)', 'Predicted EPSS Score': 'EPSS Score'})
        
        st.plotly_chart(fig_line_plot_epss)
        
