# SolarWatch ☀️

SolarWatch is an advanced endogenous version analysis dashboard built with Streamlit and powered by Gemini 2.5 Flash. It translates thousands of unstructured, multi-lingual app store reviews into actionable, quantifiable metrics to track software iteration health and agile response times.

## 🚀 Key Features

*   **Data DNA & Quantifiable Metrics**: Semantic analysis of raw user feedback to compute individual `Sentiment_Score` and Business Impact Severity (Critical/Major/Minor).
*   **Endogenous Versioning**: Bypasses external app release web scrapers. Automatically detects and reconstructs app release lifecycles and "Blast Radius" entirely from endogenous version footprints found within user reviews.
*   **Executive Dashboards (McKinsey Style)**: 
    *   **Health Leaderboard**: A severity-weighted leaderboard exposing the true system health of recent updates.
    *   **Persona Pain Point Mismatch**: Identifies discrepancies between installer and homeowner priorities.
    *   **Iteration Gantt Chart**: Plots the timeline and lifecycle length of consecutive app versions.
*   **Interactive Data Explorer**: A macro-to-micro drill-down component allowing precise navigation from global KPIs directly to original user sentences and AI-extracted evidence quotes.

## 🛠️ Tech Stack

*   **Frontend**: Streamlit, Plotly
*   **Data Processing**: Pandas, SQLite
*   **AI Engine**: Google Gemini 2.5 Flash

## ⚖️ Compliance & Privacy

This application analyzes public reviews from the App Store and Google Play. All displayed user contents are dynamically processed through an in-memory PII (Personally Identifiable Information) masking engine before rendering, ensuring emails and phone numbers are securely redacted.

---
*Developed for strategic PV software industry analysis.*