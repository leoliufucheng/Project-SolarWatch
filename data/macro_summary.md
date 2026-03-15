# SolarWatch Cognitive Pipeline — Macro Aggregation Report

## Pipeline Overview

- **Raw Reviews**: 4381
- **Sent to LLM**: 4381
- **Processed Records**: 4381
- **Valid (hallucination guard passed)**: 4209 (96.1%)
- **Remaining**: 0

## Table 1: Android Penalty Effect (安卓惩罚效应验证)

**Purpose**: Verify hypothesis that Android reviews are more negative than iOS for the same brand.

| App | Platform | Count | Avg Sentiment | Avg Rating |
|-----|----------|------:|:-------------:|:----------:|
| Enphase Enlighten | app_store | 19 | -0.18 | 3.32 |
| Enphase Enlighten | google_play | 142 | +0.41 | 4.04 |
| Fronius Solar.web | app_store | 109 | -0.50 | 2.18 |
| Fronius Solar.web | google_play | 358 | -0.53 | 2.23 |
| Huawei FusionSolar | app_store | 2245 | +0.49 | 4.31 |
| SMA Energy | app_store | 112 | -0.36 | 2.60 |
| SMA Energy | google_play | 389 | -0.09 | 3.13 |
| SolarEdge | app_store | 146 | -0.62 | 2.04 |
| SolarEdge | google_play | 485 | -0.45 | 2.38 |
| Sungrow iSolarCloud | app_store | 59 | -0.35 | 2.81 |
| Sungrow iSolarCloud | google_play | 145 | -0.27 | 2.59 |

### Android vs iOS Sentiment Delta

| App | Δ Sentiment (Android − iOS) | Δ Rating | Verdict |
|-----|:---------------------------:|:--------:|---------|
| Enphase Enlighten | +0.59 | +0.72 | Android better |
| Fronius Solar.web | -0.03 | +0.05 | No significant difference |
| Huawei FusionSolar | N/A (iOS only, 2245 reviews) | N/A | No Android data |
| SMA Energy | +0.27 | +0.53 | Android better |
| SolarEdge | +0.17 | +0.34 | Android better |
| Sungrow iSolarCloud | +0.08 | -0.22 | Android better |

## Table 2: Installer Density (安装商浓度)

**Purpose**: Detect B2B installer personas hidden among B2C homeowner reviews.
**Global installer rate**: 26/4209 (0.6%)

| App | Total Valid | Installers | Installer % |
|-----|:----------:|:----------:|:-----------:|
| Sungrow iSolarCloud | 204 | 3 | 1.5% |
| SMA Energy | 501 | 5 | 1.0% |
| Huawei FusionSolar | 2245 | 14 | 0.6% |
| SolarEdge | 631 | 3 | 0.5% |
| Fronius Solar.web | 467 | 1 | 0.2% |
| Enphase Enlighten | 161 | 0 | 0.0% |

## Table 3: Top 10 Critical Root Causes (全局致命痛点)

**Purpose**: Identify the most impactful system-level issues across the European PV app market.
**Filter**: Only Major or Critical severity.

| Rank | Root Cause | Occurrences | Avg Sentiment | Affected Apps |
|:----:|-----------|:-----------:|:-------------:|---------------|
| 1 | Login Failure | 24 | -0.90 | Huawei FusionSolar,SMA Energy,Fronius Solar.web,SolarEdge |
| 2 | Data Inaccuracy | 21 | -0.69 | Huawei FusionSolar,SolarEdge,Enphase Enlighten |
| 3 | App Not Functioning | 21 | -0.95 | Huawei FusionSolar,SMA Energy,Fronius Solar.web,SolarEdge |
| 4 | UI/UX Regression | 14 | -0.77 | Huawei FusionSolar,Fronius Solar.web,SolarEdge |
| 5 | Update Regression | 13 | -0.84 | Huawei FusionSolar,Sungrow iSolarCloud,Fronius Solar.web,SolarEdge |
| 6 | App Instability | 11 | -0.66 | Huawei FusionSolar,SMA Energy,Fronius Solar.web,SolarEdge |
| 7 | Data Latency | 10 | -0.68 | Huawei FusionSolar,SMA Energy,SolarEdge |
| 8 | UI/UX Regression after Update | 8 | -0.84 | SolarEdge |
| 9 | Missing Consumption Data | 8 | -0.71 | Huawei FusionSolar,SMA Energy,Fronius Solar.web,SolarEdge |
| 10 | Frequent App Crashes | 8 | -0.81 | Huawei FusionSolar,SMA Energy,Fronius Solar.web,SolarEdge |

## Table 4: Category Heatmap (4+1 业务域火力分布)

**Purpose**: Distribution of review complaints across the 5 business domains.

| Category | Count | Share % | Avg Sentiment | Critical | Major | Minor |
|----------|------:|:-------:|:-------------:|:--------:|:-----:|:-----:|
| O&M | 1962 | 46.6% | +0.30 | 113 | 482 | 1367 |
| DevOps | 1930 | 45.9% | -0.03 | 208 | 562 | 1160 |
| Ecosystem | 179 | 4.3% | -0.09 | 12 | 76 | 91 |
| Localization | 71 | 1.7% | -0.16 | 3 | 24 | 44 |
| Commissioning | 67 | 1.6% | -0.39 | 14 | 37 | 16 |

