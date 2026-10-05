use serde_json::Value;
use trading_signals_text_tokens::tokens::{
    Signal, Symbol, SymbolClass, SymbolType, Target,
};
use crate::models::TradeRequest;

/// Utility helper to parse duration from a PeriodTime string like "M1", "M5", "H1", "60", "300".
pub fn parse_period_time_to_seconds(period: &str) -> i64 {
    let p = period.trim().to_uppercase();
    if p.starts_with('M') {
        if let Ok(mins) = p[1..].parse::<i64>() {
            return mins * 60;
        }
    } else if p.ends_with('M') {
        if let Ok(mins) = p[..p.len() - 1].parse::<i64>() {
            return mins * 60;
        }
    } else if p.starts_with('H') {
        if let Ok(hours) = p[1..].parse::<i64>() {
            return hours * 3600;
        }
    } else if p.ends_with('H') {
        if let Ok(hours) = p[..p.len() - 1].parse::<i64>() {
            return hours * 3600;
        }
    } else if p.ends_with('S') {
        if let Ok(secs) = p[..p.len() - 1].parse::<i64>() {
            return secs;
        }
    }
    
    p.parse::<i64>().unwrap_or(60)
}

/// Extract clean symbol string from Symbol struct
pub fn extract_symbol_name(symbol: &Symbol) -> String {
    let base_name = match &symbol.symbol_type {
        SymbolType::Crypto(s) => s.clone(),
        SymbolType::Etf(s) => s.clone(),
        SymbolType::Forex(s) => s.clone(),
        SymbolType::Funds(s) => s.clone(),
        SymbolType::Index(s) => s.clone(),
        SymbolType::MoneyMarkets(s) => s.clone(),
        SymbolType::Stock(s) => s.clone(),
        SymbolType::Plain(s) => s.clone(),
        SymbolType::Empty(s) => s.clone(),
    };

    if symbol.symbol_class == Some(SymbolClass::Otc) && !base_name.to_uppercase().contains("OTC") {
        format!("{}_OTC", base_name)
    } else {
        base_name
    }
}

/// Converts a single `Signal` into a `TradeRequest` for a specific broker and credentials,
/// with an optional fallback timezone in case the binary signal does not define one.
/// Target::PeriodTime is used for Binary Options (setting duration).
/// Target::ProfitLoss is used for Market Operations (setting sl / tp).
pub fn signal_to_trade_request_with_timezone(
    signal: &Signal,
    broker_code: &str,
    credentials: Value,
    default_amount: f64,
    fallback_timezone: Option<&str>,
) -> Result<TradeRequest, String> {
    let action = match signal.action {
        Some(true) => "buy".to_string(),
        Some(false) => "sell".to_string(),
        None => return Err("Signal is missing action (buy/sell)".to_string()),
    };

    let asset = match &signal.symbol {
        Some(s) => extract_symbol_name(s),
        None => return Err("Signal is missing symbol".to_string()),
    };

    let mut duration: Option<i64> = None;
    let mut sl: Option<f64> = None;
    let mut tp: Option<f64> = None;

    if let Some(ref target) = signal.target {
        match target {
            Target::PeriodTime(period_str) => {
                // Target::PeriodTime is for binary options
                let secs = parse_period_time_to_seconds(period_str);
                duration = Some(secs);
            }
            Target::ProfitLoss(prices_target) => {
                // Target::ProfitLoss is for market operations (Forex / CFD / MT5)
                if prices_target.stoploss > 0.0 {
                    sl = Some(prices_target.stoploss as f64);
                }
                if let Some(&first_tp) = prices_target.profits.first() {
                    if first_tp > 0.0 {
                        tp = Some(first_tp as f64);
                    }
                }
            }
        }
    }

    let mut entry_time: Option<String> = None;
    let mut timezone: Option<String> = None;
    let mut entry_price: Option<f64> = None;
    let mut entry_range: Option<(f64, f64)> = None;
    let mut verify_price: Option<bool> = None;

    if let Some(ref entry) = signal.entry {
        match entry {
            trading_signals_text_tokens::tokens::Entry::TimeEntry(tz, t) => {
                if !t.is_empty() {
                    entry_time = Some(t.clone());
                }
                if !tz.is_empty() {
                    timezone = Some(tz.clone());
                }
            }
            trading_signals_text_tokens::tokens::Entry::TimePrice(tz, p) => {
                if !tz.is_empty() {
                    timezone = Some(tz.clone());
                }
                if *p > 0.0 {
                    entry_price = Some(*p as f64);
                    verify_price = Some(true);
                }
            }
            trading_signals_text_tokens::tokens::Entry::PriceEntry(p) => {
                if *p > 0.0 {
                    entry_price = Some(*p as f64);
                    verify_price = Some(true);
                }
            }
            trading_signals_text_tokens::tokens::Entry::EntryRange(p1, p2) => {
                if *p1 > 0.0 && *p2 > 0.0 {
                    entry_range = Some((*p1 as f64, *p2 as f64));
                    verify_price = Some(true);
                }
            }
        }
    }

    if timezone.is_none() {
        if let Some(fb_tz) = fallback_timezone.filter(|s| !s.trim().is_empty()) {
            timezone = Some(fb_tz.trim().to_string());
        }
    }

    if signal.is_binary() && timezone.is_none() {
        return Err("Binary signal cannot be executed: timezone is not specified in signal or database".to_string());
    }

    let mut gale_steps: Option<i64> = None;
    for g in &signal.gales {
        match g {
            trading_signals_text_tokens::tokens::Gale::Number(n) => {
                gale_steps = Some(*n as i64);
            }
            trading_signals_text_tokens::tokens::Gale::NoGale => {
                gale_steps = Some(0);
            }
            _ => {}
        }
    }

    Ok(TradeRequest {
        broker: broker_code.to_string(),
        credentials,
        action,
        asset,
        amount: default_amount,
        duration,
        sl,
        tp,
        timezone,
        entry_time,
        entry_price,
        entry_range,
        verify_price,
        tolerance: Some(0.0001),
        gale_steps,
        gale_multiplier: Some(2.0),
        price_timeout: Some(60),
        metric_id: None,
    })
}

/// Verifies if a given market price matches the signal's Entry criteria.
/// - `TimeEntry`: Always valid (does not depend on price).
/// - `EntryRange(p1, p2)`: Valid if `min - tol <= current_price <= max + tol`.
/// - `PriceEntry(p)` / `TimePrice(_, p)`: Valid if `current_price` satisfies entry price condition.
pub fn verify_signal_entry_price(
    signal: &Signal,
    current_price: f64,
    tolerance: Option<f64>,
) -> Result<bool, String> {
    match &signal.entry {
        Some(entry) => {
            let tol = tolerance.unwrap_or(0.0001) as f32;
            let valid = entry.is_price_valid(current_price as f32, signal.action, Some(tol));
            if valid {
                Ok(true)
            } else {
                Err(format!(
                    "Current price {:.5} does not satisfy signal entry condition {:?}",
                    current_price, entry
                ))
            }
        }
        None => Ok(true),
    }
}

/// Converts a single `Signal` into a `TradeRequest` for a specific broker and credentials.
pub fn signal_to_trade_request(
    signal: &Signal,
    broker_code: &str,
    credentials: Value,
    default_amount: f64,
) -> Result<TradeRequest, String> {
    signal_to_trade_request_with_timezone(signal, broker_code, credentials, default_amount, None)
}

/// Converts a `Vec<Signal>` into a `Vec<TradeRequest>`.
pub fn signals_to_trade_requests(
    signals: &[Signal],
    broker_code: &str,
    credentials: Value,
    default_amount: f64,
) -> Vec<TradeRequest> {
    signals
        .iter()
        .filter_map(|sig| signal_to_trade_request(sig, broker_code, credentials.clone(), default_amount).ok())
        .collect()
}

/// Serializes a `Vec<Signal>` to a JSON string.
pub fn signals_to_json(signals: &[Signal]) -> Result<String, serde_json::Error> {
    serde_json::to_string(signals)
}

/// Deserializes a JSON string to a `Vec<Signal>`.
pub fn json_to_signals(json_str: &str) -> Result<Vec<Signal>, serde_json::Error> {
    serde_json::from_str(json_str)
}

#[cfg(test)]
mod tests {
    use super::*;
    use trading_signals_text_tokens::tokens::{Signal, Symbol, SymbolType, Target, Entry};

    #[test]
    fn test_signal_to_trade_request_with_timezone_fallback() {
        let mut sig = Signal::default();
        sig.action = Some(true);
        sig.symbol = Some(Symbol {
            symbol_type: SymbolType::Forex("EURUSD".to_string()),
            symbol_class: None,
        });
        sig.target = Some(Target::PeriodTime("M5".to_string()));
        sig.entry = Some(Entry::TimeEntry("".to_string(), "14:30:00".to_string()));

        // Without timezone in signal or fallback -> MUST fail (no default assumption)
        let res_err = signal_to_trade_request(&sig, "quotex", serde_json::json!({}), 10.0);
        assert!(res_err.is_err(), "Binary signal without timezone must be rejected");

        // With fallback timezone -> succeeds
        let req2 = signal_to_trade_request_with_timezone(&sig, "quotex", serde_json::json!({}), 10.0, Some("UTC-3")).unwrap();
        assert_eq!(req2.timezone, Some("UTC-3".to_string()));
        assert_eq!(req2.entry_time, Some("14:30:00".to_string()));
        assert_eq!(req2.duration, Some(300));
    }

    #[test]
    fn test_signal_to_trade_request_with_entry_prices() {
        use trading_signals_text_tokens::tokens::SymbolClass;

        // 1. EntryRange signal
        let mut sig_range = Signal::default();
        sig_range.action = Some(true); // Buy
        sig_range.symbol = Some(Symbol {
            symbol_type: SymbolType::Forex("EURUSD".to_string()),
            symbol_class: Some(SymbolClass::Otc),
        });
        sig_range.target = Some(Target::PeriodTime("M1".to_string()));
        sig_range.entry = Some(Entry::EntryRange(1.0850, 1.0860));

        let req_range = signal_to_trade_request_with_timezone(&sig_range, "pocketoption", serde_json::json!({}), 5.0, Some("UTC")).unwrap();
        assert_eq!(req_range.asset, "EURUSD_OTC");
        let (p1, p2) = req_range.entry_range.unwrap();
        assert!((p1 - 1.0850).abs() < 1e-4);
        assert!((p2 - 1.0860).abs() < 1e-4);
        assert_eq!(req_range.verify_price, Some(true));
        assert!(verify_signal_entry_price(&sig_range, 1.0855, None).is_ok());
        assert!(verify_signal_entry_price(&sig_range, 1.0870, None).is_err());

        // 2. PriceEntry signal
        let mut sig_price = Signal::default();
        sig_price.action = Some(false); // Sell
        sig_price.symbol = Some(Symbol {
            symbol_type: SymbolType::Crypto("BTCUSDT".to_string()),
            symbol_class: None,
        });
        sig_price.target = Some(Target::PeriodTime("M5".to_string()));
        sig_price.entry = Some(Entry::PriceEntry(65000.0));

        let req_price = signal_to_trade_request_with_timezone(&sig_price, "quotex", serde_json::json!({}), 20.0, Some("UTC")).unwrap();
        assert_eq!(req_price.asset, "BTCUSDT");
        assert_eq!(req_price.entry_price, Some(65000.0));
        assert_eq!(req_price.verify_price, Some(true));
        // Sell: price >= 65000 is good entry
        assert!(verify_signal_entry_price(&sig_price, 65010.0, None).is_ok());
        assert!(verify_signal_entry_price(&sig_price, 64900.0, None).is_err());

        // 3. TimePrice signal
        let mut sig_time_price = Signal::default();
        sig_time_price.action = Some(true); // Buy
        sig_time_price.symbol = Some(Symbol {
            symbol_type: SymbolType::Stock("AAPL".to_string()),
            symbol_class: None,
        });
        sig_time_price.entry = Some(Entry::TimePrice("UTC-4".to_string(), 220.0));
        sig_time_price.target = Some(Target::PeriodTime("H1".to_string()));

        let req_time_price = signal_to_trade_request(&sig_time_price, "metatrader5", serde_json::json!({}), 1.0).unwrap();
        assert_eq!(req_time_price.asset, "AAPL");
        assert_eq!(req_time_price.timezone, Some("UTC-4".to_string()));
        assert_eq!(req_time_price.entry_price, Some(220.0));
        // Buy: price <= 220 is good entry
        assert!(verify_signal_entry_price(&sig_time_price, 219.5, None).is_ok());
        assert!(verify_signal_entry_price(&sig_time_price, 221.0, None).is_err());
    }
}
