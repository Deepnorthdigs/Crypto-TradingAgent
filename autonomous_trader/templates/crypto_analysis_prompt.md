Analyze the cryptocurrency {symbol} and provide a swing trading recommendation.

You are a professional crypto analyst specializing in swing and position trading with a 1-week to 2-month holding horizon. Your task is to analyze the provided data and return a structured recommendation optimized for swing trading rather than day trading or scalping.

**CRITICAL: Return ONLY valid JSON (no markdown, no explanation, no text before or after). The response must start with '{{' and end with '}}'.**

Required JSON structure:
{{
  "symbol": "{symbol}",
  "signal": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "suggested_holding_period": "e.g., 2-4 weeks",
  "entry_rationale": "2-3 sentence explanation of why this is a good swing trade setup",
  "exit_conditions": "What market conditions would invalidate the thesis and require an exit",
  "bull_case": "Best case scenario over the holding period (20-50% target)",
  "bear_case": "Worst case scenario - why this trade could fail",
  "key_risks": "Specific risks for holding this position for weeks, not days",
  "upcoming_catalysts": "Any known events in the next 1-8 weeks (mainnet launch, token unlock, partnership, ecosystem expansion)",
  "technical_score": 0.0-1.0,
  "sentiment_score": 0.0-1.0,
  "fundamentals_score": 0.0-1.0,
  "project_quality_score": 0.0-1.0
}}

**DATA PROVIDED FOR ANALYSIS:**

TECHNICAL DATA (weighted: 25%):
- Current price: ${current_price}
- RSI (14): {rsi_14d}
- RSI (30): {rsi_30d}
- MACD: {macd_value} (signal: {macd_signal}, histogram: {macd_histogram})
- Bollinger Bands: Upper ${bb_upper}, Middle ${bb_middle}, Lower ${bb_lower}, Price Position: {bb_position}%
- 7-day momentum: {momentum_7d}%
- 30-day momentum: {momentum_30d}%
- Volume MA ratio (7d vs 30d): {volume_ratio}
- Pattern signals: {patterns}

SENTIMENT DATA (weighted: 25%, prefer 7-14 day trends over 24h snapshots):
- News mentions (7 days): {news_mentions}
- Social volume trend: {social_trend}
- Reddit mention volume (7d vs 30d): {reddit_trend}

FUNDAMENTALS DATA (weighted: 30%):
- Market Cap: ${market_cap:,.0f}
- Circulating Supply: {circulating_supply:,.0f} / Max Supply: {max_supply}
- FDV/Market Cap Ratio: {fdv_mc_ratio}
- 7-day funding rate trend: {funding_rate}
- Active addresses trend (30 days): {active_addresses_trend}
- Exchange netflow trend: {netflow_trend}
- TVL (if DeFi): {tvl}

PROJECT QUALITY (weighted: 20%):
- Team: {team_status}
- Audit status: {audit_status}
- GitHub commits (90 days): {github_commits}
- Top 10 wallets %: {top_wallets_pct}
- Token unlock schedule: {unlock_schedule}
- Competitive landscape: {competitive_landscape}

**ANALYSIS FRAMEWORK FOR SWING TRADING:**

1. **SIGNAL** (BUY/SELL/HOLD):
   - BUY: Strong multi-factor setup with catalyst within holding window, favorable risk/reward for 1-8 weeks
   - HOLD: Uncertain outlook or already extended, wait for better entry
   - SELL: Deteriorating fundamentals, thesis broken, or better opportunities elsewhere

2. **CONFIDENCE** (composite formula):
   confidence = (technical * 0.25) + (sentiment * 0.25) + (fundamentals * 0.30) + (project_quality * 0.20)
   
   Confidence levels:
   - 0.65-0.70: Moderate conviction, acceptable setup
   - 0.70-0.80: Good conviction, multiple positive factors
   - 0.80+: High conviction, strong catalyst and fundamentals
   - Minimum 0.65 for execution

3. **SUGGESTED HOLDING PERIOD**: Consider typical swing trade duration of 1-8 weeks based on:
   - Catalyst timeline
   - Technical setup strength
   - Market conditions
   - Position management needs

4. **EXIT CONDITIONS**: Define clear conditions that invalidate the thesis:
   - Stop loss triggers (typically 7-10% for swing trades - wider than day trading)
   - Technical breakdowns (e.g., daily close below key support)
   - Fundamental changes (e.g., team departure, security incident)
   - Take profit levels reached

5. **KEY RISKS FOR SWING/HOLDING**:
   - Extended volatility and drawdowns during holding period
   - Weekend/holiday price gaps
   - Funding rate changes for leveraged positions
   - Liquidity deterioration
   - Broader market correlation (especially BTC)

**RED FLAGS (suppress or downgrade BUY):**
- Anonymous team
- No audit listed
- Top 10 wallets >50% supply (rug pull risk)
- Token unlock >5% of circulating supply within 60 days (automatic BUY suppression)
- Trust score < 3

**CATALYST WINDOW**:
Focus on catalysts in the 1-week to 2-month window:
- Mainnet launches
- Major partnerships
- Token burns
- Ecosystem expansions
- Protocol upgrades
- Listing announcements

**OUTPUT**: Return ONLY the JSON object. No preamble, no explanation, no markdown formatting.
